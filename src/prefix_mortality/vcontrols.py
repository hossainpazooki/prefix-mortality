"""The two controls on the V instrument, run against one vLLM server under one block size.

Per repetition, three requests as on the L instrument: a first request under a fresh nonce (write),
the same bytes again (read), and a request under another fresh nonce whose system text is random
words of the same token length (scramble). What is new against L: the write side is measured, not
inferred (`created_cache_tokens` counts the full blocks a request stored), and the zeros are exact,
not bounds, because a block matches only whole. `summarize_vcontrols` states the rules and recomputes
the verdict from disk; this module sends, records, and stops at the first repetition that fails.

`run` refuses unless `config/controls.toml` and `config/vllm.toml` are registered, the block size is
a registered one, every pinned model file hashes to its digest, the server reports the pinned version
and serves the registered model name. The server does not report its block size: the run script
passes it, each run gets a freshly started server, and the records read the block size back only
through the block arithmetic of the readings. `probe` sends a write, a read and a second-nonce write,
prints what came back and records nothing; `--pad-words N` lengthens the user message so a boundary
(n or n+1 a multiple of the block) can be hunted before registration.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import (FAMILY_FILES, ControlsConfig, VFamilyConfig, VllmConfig,
                                     load_controls_config, load_vfamily_config, load_vllm_config)
from prefix_mortality.controls import FIXTURE, Refusal
from prefix_mortality.hashing import sha256_file_bytes, sha256_text_file
from prefix_mortality.nonce import new_nonce
from prefix_mortality.record import SCHEMA_VERSION, append, body_bytes, store_request, utc_now
from prefix_mortality.rng import make_rng
from prefix_mortality.summarize_vcontrols import _lcp, evaluate, render
from prefix_mortality.vllm import Client, EngineError, observed


def build_body(cfg: ControlsConfig, served: str, system_text: str, tools: list, nonce: str,
               user_message: str | None = None, template_kwargs: dict | None = None) -> bytes:
    # tool_choice "none": the server refuses tools under the default "auto" choice unless it runs a
    # tool-call parser; "none" keeps the tools in the rendered prompt without enabling call parsing.
    body: dict = {"model": served,
                  "messages": [{"role": "system", "content": f"run {nonce}\n{system_text}"},
                               {"role": "user", "content": user_message or cfg.user_message}],
                  "tools": tools, "tool_choice": "none", "max_tokens": cfg.max_tokens,
                  "temperature": cfg.temperature, "stream": False}
    if template_kwargs is not None:
        body["chat_template_kwargs"] = template_kwargs
    return body_bytes(body)


def scramble_text(client: Client, rng, system_text: str) -> str:
    """Words drawn at random from the system text's own words, cut to the system text's token length,
    counted by the server's own tokenizer with no special tokens added."""
    words = system_text.split()
    target = client.count_text(system_text)
    drawn = [words[int(i)] for i in rng.integers(0, len(words), size=len(words) + len(words))]
    lo, hi = 1, len(drawn)
    while lo < hi:
        mid = (lo + hi) // 2
        if client.count_text(" ".join(drawn[:mid])) < target:
            lo = mid + 1
        else:
            hi = mid
    return " ".join(drawn[:lo])


def _maybe_vfamily(cfg: VllmConfig, family: str) -> VFamilyConfig | None:
    """The family's own pin file on this lane (config.FAMILY_FILES, e.g. vsm3.toml for smollm3), when
    the family is not one of vllm.toml's. An unknown family is refused with every known family named."""
    if any(m.family == family for m in cfg.models):
        return None
    fname = (FAMILY_FILES.get(family) or (None, None))[1]
    if fname is None:
        raise Refusal(f"no model of family {family!r}: vllm.toml has {[m.family for m in cfg.models]}, "
                      f"family files cover {sorted(k for k, v in FAMILY_FILES.items() if v[1])}")
    vfam = load_vfamily_config(REPO_ROOT / "config" / fname)
    if vfam.model.family != family:
        raise Refusal(f"no model of family {family!r}: vllm.toml has {[m.family for m in cfg.models]}, "
                      f"{fname} has {vfam.model.family!r}")
    return vfam


def _family_model(cfg: VllmConfig, family: str, vfam: VFamilyConfig | None):
    """The family's model pin and served name: vllm.toml's, or the family file's."""
    if vfam is not None and family == vfam.model.family:
        return vfam.model, vfam.served_model_name
    return cfg.model(family), cfg.served_model_name


def _gate_local(controls: ControlsConfig, cfg: VllmConfig, family: str, block_size: int, model_dir: Path,
                vfam: VFamilyConfig | None = None) -> None:
    """Everything that can be refused before the server is contacted."""
    gated = [(controls.config_path.name, controls.registered_by), (cfg.config_path.name, cfg.registered_by)]
    if vfam is not None and family == vfam.model.family:
        gated.append((vfam.config_path.name, vfam.registered_by))
    for name, reg in gated:
        if not reg:
            raise Refusal(f"{name} is UNREGISTERED (registered_by is empty); a ledger entry registers it first")
    if block_size not in cfg.block_sizes:
        raise Refusal(f"block size {block_size} is not registered; registered: {list(cfg.block_sizes)}")
    model, _ = _family_model(cfg, family, vfam)
    for f in model.files:
        p = Path(model_dir) / f.name
        if not p.is_file():
            raise Refusal(f"model file {p} does not exist")
        digest = sha256_file_bytes(p)
        if digest != f.sha256:
            raise Refusal(f"{p} hashes to {digest}, config pins {f.sha256}")


def _gate_server(cfg: VllmConfig, client: Client, served: str | None = None) -> dict:
    served = cfg.served_model_name if served is None else served
    version = client.version()
    if version != cfg.version:
        raise Refusal(f"the server reports version {version!r}; config pins {cfg.version!r}")
    ids = client.model_ids()
    if served not in ids:
        raise Refusal(f"the server serves {ids}; config pins {served!r}")
    return {"version": version, "model_ids": ids}


def _send(client: Client, body: bytes, requests_dir: Path) -> tuple[str, dict, str, str]:
    prepared = client.prepare(body)
    sha = store_request(requests_dir, body, prepared["rendered"], prepared["tokens"])
    start = utc_now()
    response = client.chat(body)
    return sha, response, start, utc_now()


def run(controls: ControlsConfig, cfg: VllmConfig, family: str, block_size: int, client: Client,
        model_dir: Path, repo_root: Path = REPO_ROOT, fixture: Path = FIXTURE,
        vfam: VFamilyConfig | None = None) -> dict:
    _gate_local(controls, cfg, family, block_size, Path(model_dir), vfam)
    model, served = _family_model(cfg, family, vfam)
    server = _gate_server(cfg, client, served)
    system_text = (fixture / "system.txt").read_bytes().decode("utf-8")
    tools = json.loads((fixture / "tools.json").read_text(encoding="utf-8"))
    requests_dir = repo_root / "corpus" / "requests"
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{family}-b{block_size}"
    log = cfg.corpus_dir / f"{run_id}.jsonl"
    if log.exists():
        raise Refusal(f"{log} already exists; a run never appends to another run's records")
    hashes = {"controls": sha256_text_file(controls.config_path), "vllm": sha256_text_file(cfg.config_path)}
    if vfam is not None and family == vfam.model.family:
        hashes[vfam.config_path.stem] = sha256_text_file(vfam.config_path)   # "vsm3", ...
    base = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "experiment": "vcontrols", "family": family,
            "engine_repo": cfg.repo, "engine_commit": cfg.commit, "engine_version": cfg.version,
            "served_model_name": served, "dtype": cfg.dtype, "max_model_len": cfg.max_model_len,
            "kvcache_space_gib": cfg.kvcache_space_gib, "block_size": block_size,
            "model_hf_repo": model.hf_repo, "model_files": [{"name": f.name, "sha256": f.sha256} for f in model.files],
            "server": server,
            "config_sha256": hashes}
    rng = make_rng(controls.seed)
    records, seq = [], 0
    for rep in range(1, controls.repetitions + 1):
        nonce = new_nonce(controls.nonce_bytes)
        write = build_body(controls, served, system_text, tools, nonce)
        other = new_nonce(controls.nonce_bytes)
        scramble = build_body(controls, served, scramble_text(client, rng, system_text), tools, other)
        for control, body, n in (("write", write, nonce), ("read", write, nonce), ("scramble", scramble, other)):
            sha, response, start, end = _send(client, body, requests_dir)
            seq += 1
            rec = {**base, "seq": seq, "repetition": rep, "control": control, "nonce": n,
                   "request_sha256": sha, "ts_start": start, "ts_end": end,
                   "local_date": datetime.now().strftime("%Y-%m-%d"), "observed": observed(response),
                   "usage_raw": response.get("usage")}
            append(log, rec)
            records.append(rec)
        report = evaluate(records, requests_dir, cfg.block_sizes,
                          controls.length_tolerance_tokens)
        if report["verdict"] != "PASS":
            break
    out = cfg.results_dir / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                     newline="\n")
    return report


def probe(controls: ControlsConfig, cfg: VllmConfig, client: Client, fixture: Path = FIXTURE,
          pad_words: int = 0, served: str | None = None) -> dict:
    """Unrecorded. `served` names the model id to address (a later family's); default vllm.toml's."""
    served = cfg.served_model_name if served is None else served
    server = {"version": client.version(), "model_ids": client.model_ids()}
    system_text = (fixture / "system.txt").read_bytes().decode("utf-8")
    tools = json.loads((fixture / "tools.json").read_text(encoding="utf-8"))
    user = controls.user_message + " pad" * pad_words
    nonce, other = new_nonce(controls.nonce_bytes), new_nonce(controls.nonce_bytes)
    write = build_body(controls, served, system_text, tools, nonce, user_message=user)
    fresh = build_body(controls, served, system_text, tools, other, user_message=user)
    pw, pf = client.prepare(write), client.prepare(fresh)
    ids_w, ids_f = [t["id"] for t in pw["tokens"]], [t["id"] for t in pf["tokens"]]
    first, second, third = client.chat(write), client.chat(write), client.chat(fresh)
    return {"server": server, "prompt_tokens": len(ids_w), "pad_words": pad_words,
            "n_mod": {str(b): len(ids_w) % b for b in cfg.block_sizes},
            "shared_head_tokens_across_nonces": _lcp(ids_w, ids_f),
            "nonce_in_rendered": nonce in pw["rendered"],
            "write": observed(first), "read": observed(second), "fresh_nonce": observed(third),
            "usage_raw_write": first.get("usage")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.vcontrols")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "probe"):
        p = sub.add_parser(name)
        p.add_argument("--url", required=True, help="the server's address, e.g. http://127.0.0.1:8081")
    sub.choices["run"].add_argument("--family", required=True)
    sub.choices["run"].add_argument("--block-size", type=int, required=True)
    sub.choices["run"].add_argument("--model-dir", required=True, help="folder holding the pinned model files")
    sub.choices["probe"].add_argument("--pad-words", type=int, default=0,
                                      help="lengthen the user message to hunt a block boundary")
    sub.choices["probe"].add_argument("--served-model", default=None,
                                      help="model id to address when the server is not vllm.toml's (a smoke of a later family)")
    a = ap.parse_args(argv)
    controls = load_controls_config(REPO_ROOT / "config" / "controls.toml", REPO_ROOT)
    cfg = load_vllm_config(REPO_ROOT / "config" / "vllm.toml", REPO_ROOT)
    client = Client(a.url, controls.request_timeout_seconds)
    try:
        if a.cmd == "probe":
            print(json.dumps(probe(controls, cfg, client, pad_words=a.pad_words, served=a.served_model),
                             indent=2, ensure_ascii=True))
            return 0
        vfam = _maybe_vfamily(cfg, a.family)
        report = run(controls, cfg, a.family, a.block_size, client, Path(a.model_dir), vfam=vfam)
    except (Refusal, EngineError, ValueError) as e:
        print(f"VCONTROLS REFUSED: {e}".encode("ascii", "backslashreplace").decode("ascii"), file=sys.stderr)
        return 2
    print(render(report).encode("ascii", "backslashreplace").decode("ascii"))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
