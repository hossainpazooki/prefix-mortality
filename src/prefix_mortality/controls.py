"""The two controls, run against one engine serving one model.

Per repetition, three requests: a first request under a fresh nonce (write), the same bytes again
(read), and a request under another fresh nonce whose system text is random words of the same length
(scramble). `summarize` states the rules and recomputes the verdict from disk; this module sends,
records, and stops at the first repetition that fails.

`run` refuses unless both configs are registered, the local model file hashes to the configured
digest, and the server reports the pinned build. `probe` sends one write and one read, prints what
came back and records nothing: it is for bringing an instrument up, and it decides nothing.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import (FAMILY_FILES, ControlsConfig, EngineConfig, L17Config,
                                     load_controls_config, load_engines_config, load_l17_config)
from prefix_mortality.hashing import sha256_file_bytes, sha256_text_file
from prefix_mortality.llamacpp import Client, EngineError, observed
from prefix_mortality.nonce import new_nonce
from prefix_mortality.record import SCHEMA_VERSION, append, body_bytes, store_request, utc_now
from prefix_mortality.rng import make_rng
from prefix_mortality.summarize import evaluate, header_tokens, render

FIXTURE = REPO_ROOT / "corpus" / "base_prefix" / "tau2-airline"


class Refusal(RuntimeError):
    pass


def _maybe_l17(engine: EngineConfig, family: str) -> L17Config | None:
    """The family's own pin file (config.FAMILY_FILES: l17.toml for qwen17, lsm3.toml for smollm3),
    when the family is not one of engines.toml's. An unknown family is refused with every known
    family named; a family file whose model is another family is refused too."""
    if any(m.family == family for m in engine.models):
        return None
    fname = (FAMILY_FILES.get(family) or (None, None))[0]
    if fname is None:
        raise Refusal(f"no model of family {family!r}: engines.toml has {[m.family for m in engine.models]}, "
                      f"family files cover {sorted(k for k, v in FAMILY_FILES.items() if v[0])}")
    l17 = load_l17_config(REPO_ROOT / "config" / fname)
    if l17.model.family != family:
        raise Refusal(f"no model of family {family!r}: engines.toml has {[m.family for m in engine.models]}, "
                      f"{fname} has {l17.model.family!r}")
    return l17


def build_body(cfg: ControlsConfig, system_text: str, tools: list, nonce: str) -> bytes:
    return body_bytes({"messages": [{"role": "system", "content": f"run {nonce}\n{system_text}"},
                                    {"role": "user", "content": cfg.user_message}],
                       "tools": tools, "max_tokens": cfg.max_tokens, "temperature": cfg.temperature,
                       "stream": False})


_TOOLS_PLACEHOLDER = "__TOOLS__"


def build_body_text(cfg: ControlsConfig, system_text: str, tools_text: str, nonce: str,
                    template_kwargs: dict | None = None) -> bytes:
    """`build_body` with the `tools` value given as JSON text, embedded byte for byte, and an optional
    `chat_template_kwargs` object. With the compact text and no kwargs the result equals `build_body`."""
    body = {"messages": [{"role": "system", "content": f"run {nonce}\n{system_text}"},
                         {"role": "user", "content": cfg.user_message}],
            "tools": _TOOLS_PLACEHOLDER, "max_tokens": cfg.max_tokens, "temperature": cfg.temperature,
            "stream": False}
    if template_kwargs is not None:
        body["chat_template_kwargs"] = template_kwargs
    raw = body_bytes(body).decode("utf-8")
    marker = json.dumps(_TOOLS_PLACEHOLDER)
    if raw.count(marker) != 1:
        raise ValueError(f"the request text contains the tools placeholder {marker}; it cannot be embedded safely")
    return raw.replace(marker, tools_text, 1).encode("utf-8")


def scramble_text(client: Client, rng, system_text: str) -> str:
    """Words drawn at random from the system text's own words, cut to the system text's token length."""
    words = system_text.split()
    target = len(client.tokenize(system_text))
    drawn = [words[int(i)] for i in rng.integers(0, len(words), size=len(words) + len(words))]
    lo, hi = 1, len(drawn)
    while lo < hi:                                  # smallest count of words that reaches the target
        mid = (lo + hi) // 2
        if len(client.tokenize(" ".join(drawn[:mid]))) < target:
            lo = mid + 1
        else:
            hi = mid
    return " ".join(drawn[:lo])


def _server(props: dict) -> dict:
    settings = props.get("default_generation_settings") if isinstance(props.get("default_generation_settings"), dict) else {}
    return {"build_info": props.get("build_info"), "total_slots": props.get("total_slots"),
            "n_ctx": settings.get("n_ctx")}


def _resolve_model(engine: EngineConfig, family: str, l17: "L17Config | None"):
    """The family's model pin: engines.toml's, or l17.toml's for the family registered there."""
    if l17 is not None and family == l17.model.family:
        return l17.model
    return engine.model(family)


def _gate_local(cfg: ControlsConfig, engine: EngineConfig, family: str, model_path: Path,
                l17: "L17Config | None" = None) -> None:
    """Everything that can be refused before the server is contacted."""
    gated = [(cfg.config_path.name, cfg.registered_by), (engine.config_path.name, engine.registered_by)]
    if l17 is not None and family == l17.model.family:
        gated.append((l17.config_path.name, l17.registered_by))
    for name, reg in gated:
        if not reg:
            raise Refusal(f"{name} is UNREGISTERED (registered_by is empty); a ledger entry registers it first")
    model = _resolve_model(engine, family, l17)
    if not Path(model_path).is_file():
        raise Refusal(f"model file {model_path} does not exist")
    digest = sha256_file_bytes(model_path)
    if digest != model.sha256:
        raise Refusal(f"{model_path} hashes to {digest}, config pins {model.sha256} for {model.file}")


def _gate_server(engine: EngineConfig, props: dict) -> None:
    build = str(props.get("build_info"))
    number, short = engine.release.lstrip("b"), engine.commit[:7]
    if number not in build or short not in build:
        raise Refusal(f"the server reports build {build!r}; config pins release {engine.release} "
                      f"at commit {short}")


def _send(client: Client, body: bytes, requests_dir: Path) -> tuple[str, list[dict], dict, str, str]:
    rendered = client.render(body)
    tokens = client.tokenize(rendered)
    sha = store_request(requests_dir, body, rendered, tokens)
    start = utc_now()
    response = client.chat(body)
    return sha, tokens, response, start, utc_now()


def run(cfg: ControlsConfig, engine: EngineConfig, family: str, client: Client, model_path: Path,
        repo_root: Path = REPO_ROOT, fixture: Path = FIXTURE, l17: "L17Config | None" = None) -> dict:
    _gate_local(cfg, engine, family, Path(model_path), l17)
    props = client.props()
    _gate_server(engine, props)
    system_text = (fixture / "system.txt").read_bytes().decode("utf-8")
    tools = json.loads((fixture / "tools.json").read_text(encoding="utf-8"))
    requests_dir = repo_root / "corpus" / "requests"
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{family}"
    log = cfg.corpus_dir / f"{run_id}.jsonl"
    if log.exists():
        raise Refusal(f"{log} already exists; a run never appends to another run's records")
    model = _resolve_model(engine, family, l17)
    hashes = {"controls": sha256_text_file(cfg.config_path), "engines": sha256_text_file(engine.config_path)}
    if l17 is not None and family == l17.model.family:
        hashes[l17.config_path.stem] = sha256_text_file(l17.config_path)   # "l17", "lsm3", ...
    base = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "experiment": "controls", "family": family,
            "engine_release": engine.release, "engine_commit": engine.commit,
            "model_file": model.file, "model_sha256": model.sha256,
            "server": _server(props), "config_sha256": hashes}
    rng = make_rng(cfg.seed)
    records, seq = [], 0
    for rep in range(1, cfg.repetitions + 1):
        nonce = new_nonce(cfg.nonce_bytes)
        write = build_body(cfg, system_text, tools, nonce)
        other = new_nonce(cfg.nonce_bytes)
        scramble = build_body(cfg, scramble_text(client, rng, system_text), tools, other)
        for control, body, n in (("write", write, nonce), ("read", write, nonce), ("scramble", scramble, other)):
            sha, _, response, start, end = _send(client, body, requests_dir)
            seq += 1
            rec = {**base, "seq": seq, "repetition": rep, "control": control, "nonce": n,
                   "request_sha256": sha, "ts_start": start, "ts_end": end,
                   "local_date": datetime.now().strftime("%Y-%m-%d"), "observed": observed(response),
                   "usage_raw": response.get("usage"), "timings_raw": response.get("timings")}
            append(log, rec)
            records.append(rec)
        report = evaluate(records, requests_dir, cfg.length_tolerance_tokens)
        if report["verdict"] != "PASS":
            break
    out = cfg.results_dir / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                     newline="\n")
    return report


def probe(cfg: ControlsConfig, client: Client, fixture: Path = FIXTURE) -> dict:
    props = client.props()
    system_text = (fixture / "system.txt").read_bytes().decode("utf-8")
    tools = json.loads((fixture / "tools.json").read_text(encoding="utf-8"))
    nonce = new_nonce(cfg.nonce_bytes)
    body = build_body(cfg, system_text, tools, nonce)
    rendered = client.render(body)
    tokens = client.tokenize(rendered)
    joined = "".join(t["piece"] for t in tokens)
    first, second = client.chat(body), client.chat(body)
    return {"server": _server(props), "prompt_tokens": len(tokens), "header_bound": header_tokens(tokens, nonce),
            "pieces_rebuild_the_rendered_prompt": joined == rendered,
            "rendered_prompt_head": rendered[:200],
            "write": {"observed": observed(first), "usage": first.get("usage"), "timings": first.get("timings")},
            "read": {"observed": observed(second), "usage": second.get("usage"), "timings": second.get("timings")}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.controls")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "probe"):
        p = sub.add_parser(name)
        p.add_argument("--url", required=True, help="the server's address, e.g. http://127.0.0.1:8080")
    sub.choices["run"].add_argument("--family", required=True)
    sub.choices["run"].add_argument("--model-path", required=True)
    a = ap.parse_args(argv)
    cfg = load_controls_config(REPO_ROOT / "config" / "controls.toml", REPO_ROOT)
    client = Client(a.url, cfg.request_timeout_seconds)
    try:
        if a.cmd == "probe":
            print(json.dumps(probe(cfg, client), indent=2, ensure_ascii=True))
            return 0
        engine = load_engines_config(REPO_ROOT / "config" / "engines.toml")["llamacpp"]
        l17 = _maybe_l17(engine, a.family)
        report = run(cfg, engine, a.family, client, Path(a.model_path), l17=l17)
    except (Refusal, EngineError, ValueError) as e:
        print(f"CONTROLS REFUSED: {e}".encode("ascii", "backslashreplace").decode("ascii"), file=sys.stderr)
        return 2
    print(render(report).encode("ascii", "backslashreplace").decode("ascii"))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
