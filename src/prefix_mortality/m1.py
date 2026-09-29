"""Edit position, run against one engine serving one model, under one hypothesis.

A trial is two requests under one fresh nonce: the base request, then the same request with one word
replaced at a registered site. The edited request is rendered, tokenized and stored before it is
sent, and its predicted reuse is a function of the two stored token lists and the registered rule,
nothing else. The record carries the prediction; `summarize_m1` states the rules and recomputes
every trial, prediction included, from disk. This module sends and records.

A prediction that is not met is a result, and the run goes on. The run stops only when a trial fails
a control or a field is NOT MEASURABLE, because nothing after that can be read.

`run` refuses unless the three configs are registered, the local model file hashes to the configured
digest, the server reports the pinned build, and the server reports the number of slots the
hypothesis requires. `probe` runs one trial per site it is given, prints what came back and records
nothing.
"""
import argparse
import dataclasses
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import (ControlsConfig, EngineConfig, M1Config, M1Hypothesis, load_controls_config,
                                     load_engines_config, load_m1_config)
from prefix_mortality.controls import FIXTURE, Refusal, _gate_local, _gate_server, _server, build_body
from prefix_mortality.edits import apply, site_names
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.llamacpp import Client, EngineError, observed
from prefix_mortality.nonce import new_nonce
from prefix_mortality.record import SCHEMA_VERSION, append, store_request, utc_now
from prefix_mortality.summarize import header_tokens
from prefix_mortality.summarize_m1 import evaluate, evaluate_trial, prediction, render


def _gate_slots(hyp: M1Hypothesis, props: dict) -> None:
    slots = props.get("total_slots")
    if slots != hyp.slots:
        raise Refusal(f"{hyp.id} requires a server reporting {hyp.slots} slot(s); this one reports {slots!r}")


def _bodies(controls: ControlsConfig, m1: M1Config, site: str, system_text: str, tools: list,
            nonce: str) -> tuple[bytes, bytes]:
    base = build_body(controls, system_text, tools, nonce)
    s, t, u = apply(site, system_text, tools, controls.user_message, m1.replacement)
    return base, build_body(dataclasses.replace(controls, user_message=u), s, t, nonce)


def _prepare(client: Client, body: bytes) -> tuple[str, list[dict]]:
    rendered = client.render(body)
    return rendered, client.tokenize(rendered)


def _ids(tokens: list[dict]) -> list[int]:
    return [t["id"] for t in tokens]


def run(m1: M1Config, controls: ControlsConfig, engine: EngineConfig, family: str, hid: str, client: Client,
        model_path: Path, repo_root: Path = REPO_ROOT, fixture: Path = FIXTURE) -> dict:
    hyp = m1.hypothesis(hid)
    if not m1.registered_by:
        raise Refusal(f"{m1.config_path.name} is UNREGISTERED (registered_by is empty); a ledger entry registers it first")
    _gate_local(controls, engine, family, Path(model_path))
    props = client.props()
    _gate_server(engine, props)
    _gate_slots(hyp, props)
    system_text = (fixture / "system.txt").read_bytes().decode("utf-8")
    tools = json.loads((fixture / "tools.json").read_text(encoding="utf-8"))
    requests_dir = repo_root / "corpus" / "requests"
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{family}-{hid}"
    log = m1.corpus_dir / f"{run_id}.jsonl"
    if log.exists():
        raise Refusal(f"{log} already exists; a run never appends to another run's records")
    common = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "experiment": "m1", "hypothesis": hid,
              "family": family, "engine_release": engine.release, "engine_commit": engine.commit,
              "model_file": engine.model(family).file, "model_sha256": engine.model(family).sha256,
              "server": _server(props),
              "config_sha256": {"controls": sha256_text_file(controls.config_path),
                                "engines": sha256_text_file(engine.config_path),
                                "m1": sha256_text_file(m1.config_path)}}
    records, seq, halted = [], 0, False
    for rep in range(1, m1.repetitions + 1):
        for site in site_names(m1):
            nonce = new_nonce(controls.nonce_bytes)
            base_body, edited_body = _bodies(controls, m1, site, system_text, tools, nonce)
            base_tokens: list[dict] = []
            for role, body in (("base", base_body), ("edited", edited_body)):
                rendered, tokens = _prepare(client, body)
                sha = store_request(requests_dir, body, rendered, tokens)
                # computed from the two stored prompts alone, before the edited request is sent
                extra = prediction(m1, hid, _ids(base_tokens), _ids(tokens)) if role == "edited" else {}
                start = utc_now()
                response = client.chat(body)
                seq += 1
                rec = {**common, "seq": seq, "repetition": rep, "site": site, "role": role, "nonce": nonce,
                       "request_sha256": sha, "ts_start": start, "ts_end": utc_now(),
                       "local_date": datetime.now().strftime("%Y-%m-%d"), "observed": observed(response),
                       "usage_raw": response.get("usage"), "timings_raw": response.get("timings"), **extra}
                append(log, rec)
                records.append(rec)
                base_tokens = tokens if role == "base" else base_tokens
            trial = evaluate_trial(records[-2], records[-1], requests_dir, m1, hid)
            if trial["failures"] or trial["unmeasurable"]:
                halted = True
                break
        if halted:
            break
    report = evaluate(records, requests_dir, m1)
    out = m1.results_dir / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                     newline="\n")
    return report


def probe(m1: M1Config, controls: ControlsConfig, hid: str, sites: list[str], client: Client,
          fixture: Path = FIXTURE) -> dict:
    m1.hypothesis(hid)
    unknown = [s for s in sites if s not in site_names(m1)]
    if unknown:
        raise Refusal(f"unknown site(s) {unknown}; known: {site_names(m1)}")
    props = client.props()
    system_text = (fixture / "system.txt").read_bytes().decode("utf-8")
    tools = json.loads((fixture / "tools.json").read_text(encoding="utf-8"))
    trials = []
    for site in sites:
        nonce = new_nonce(controls.nonce_bytes)
        base_body, edited_body = _bodies(controls, m1, site, system_text, tools, nonce)
        (_, base_tokens), (_, edited_tokens) = _prepare(client, base_body), _prepare(client, edited_body)
        p = prediction(m1, hid, _ids(base_tokens), _ids(edited_tokens))
        first, second = client.chat(base_body), client.chat(edited_body)
        trials.append({"site": site, "prompt_tokens": len(edited_tokens),
                       "header_bound": header_tokens(base_tokens, nonce), **p,
                       "share_of_the_prompt": round(p["first_differing_token"] / len(edited_tokens), 4),
                       "base": {"observed": observed(first)}, "edited": {"observed": observed(second)},
                       "match": observed(second)["cache_n"] == p["predicted_reuse"]})
    return {"server": _server(props), "hypothesis": hid, "rule": m1.hypothesis(hid).rule,
            "slots_required": m1.hypothesis(hid).slots, "trials": trials}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.m1")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "probe"):
        p = sub.add_parser(name)
        p.add_argument("--url", required=True, help="the server's address, e.g. http://127.0.0.1:8080")
        p.add_argument("--hypothesis", required=True, help="an id registered in config/m1.toml")
    sub.choices["run"].add_argument("--family", required=True)
    sub.choices["run"].add_argument("--model-path", required=True)
    sub.choices["probe"].add_argument("--sites", required=True, help="comma-separated site names")
    a = ap.parse_args(argv)
    try:
        m1 = load_m1_config(REPO_ROOT / "config" / "m1.toml", REPO_ROOT)
        controls = load_controls_config(REPO_ROOT / "config" / "controls.toml", REPO_ROOT)
        client = Client(a.url, controls.request_timeout_seconds)
        if a.cmd == "probe":
            print(json.dumps(probe(m1, controls, a.hypothesis, a.sites.split(","), client), indent=2,
                             ensure_ascii=True))
            return 0
        engine = load_engines_config(REPO_ROOT / "config" / "engines.toml")["llamacpp"]
        report = run(m1, controls, engine, a.family, a.hypothesis, client, Path(a.model_path))
    except (Refusal, EngineError, ValueError) as e:
        print(f"M1 REFUSED: {e}".encode("ascii", "backslashreplace").decode("ascii"), file=sys.stderr)
        return 2
    print(render(report).encode("ascii", "backslashreplace").decode("ascii"))
    return 0 if report["outcome"] == "ALL MATCH" else 1


if __name__ == "__main__":
    sys.exit(main())
