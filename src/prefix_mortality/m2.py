"""Serialization drift, run against one engine serving one model, under one hypothesis.

A trial is two requests under one fresh nonce: the base request, then the same request with its tools
array written differently (one of the six changes in serialize.py). Both are rendered, tokenized and
stored before the second is sent, and its predicted reuse is a function of the two stored token lists
and the hypothesis's rule, nothing else. The record carries the prediction; `summarize_m2` recomputes
every trial from disk and reports whether the render agreed with the config's reading of the parser.

A prediction that is not met is a result, and the run goes on. The run stops only when a trial fails
a control or a field is NOT MEASURABLE.

`run` refuses unless the three configs are registered, the local model file hashes to the configured
digest, the server reports the pinned build, and the server reports the number of slots the
hypothesis requires. `probe` runs one trial per change it is given, prints what came back and records
nothing.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import (ControlsConfig, EngineConfig, M2Config, RuleHypothesis, load_controls_config,
                                     load_engines_config, load_m2_config)
from prefix_mortality.controls import FIXTURE, Refusal, _gate_local, _gate_server, _server, build_body_text
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.llamacpp import Client, EngineError, observed
from prefix_mortality.nonce import new_nonce
from prefix_mortality.pairs import prediction, render_diff
from prefix_mortality.record import SCHEMA_VERSION, append, store_request, utc_now
from prefix_mortality.serialize import apply, tools_text
from prefix_mortality.summarize_m2 import MARGIN, THRESHOLD, evaluate, evaluate_trial, render


def _gate_slots(hyp: RuleHypothesis, props: dict) -> None:
    slots = props.get("total_slots")
    if slots != hyp.slots:
        raise Refusal(f"{hyp.id} requires a server reporting {hyp.slots} slot(s); this one reports {slots!r}")


def _bodies(controls: ControlsConfig, change: str, system_text: str, tools: list, nonce: str) -> tuple[bytes, bytes]:
    base = build_body_text(controls, system_text, tools_text(tools), nonce)
    return base, build_body_text(controls, system_text, apply(change, tools), nonce)


def _prepare(client: Client, body: bytes) -> tuple[str, list[dict]]:
    rendered = client.render(body)
    return rendered, client.tokenize(rendered)


def _ids(tokens: list[dict]) -> list[int]:
    return [t["id"] for t in tokens]


def run(m2: M2Config, controls: ControlsConfig, engine: EngineConfig, family: str, hid: str, client: Client,
        model_path: Path, repo_root: Path = REPO_ROOT, fixture: Path = FIXTURE) -> dict:
    hyp = m2.hypothesis(hid)
    if not m2.registered_by:
        raise Refusal(f"{m2.config_path.name} is UNREGISTERED (registered_by is empty); a ledger entry registers it first")
    _gate_local(controls, engine, family, Path(model_path))
    props = client.props()
    _gate_server(engine, props)
    _gate_slots(hyp, props)
    system_text = (fixture / "system.txt").read_bytes().decode("utf-8")
    tools = json.loads((fixture / "tools.json").read_text(encoding="utf-8"))
    requests_dir = repo_root / "corpus" / "requests"
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{family}-{hid}"
    log = m2.corpus_dir / f"{run_id}.jsonl"
    if log.exists():
        raise Refusal(f"{log} already exists; a run never appends to another run's records")
    common = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "experiment": "m2", "hypothesis": hid,
              "family": family, "engine_release": engine.release, "engine_commit": engine.commit,
              "model_file": engine.model(family).file, "model_sha256": engine.model(family).sha256,
              "server": _server(props),
              "config_sha256": {"controls": sha256_text_file(controls.config_path),
                                "engines": sha256_text_file(engine.config_path),
                                "m2": sha256_text_file(m2.config_path)}}
    records, seq, halted = [], 0, False
    for rep in range(1, m2.repetitions + 1):
        for change in m2.changes:
            nonce = new_nonce(controls.nonce_bytes)
            base_body, changed_body = _bodies(controls, change.id, system_text, tools, nonce)
            base_tokens: list[dict] = []
            for role, body in (("base", base_body), ("changed", changed_body)):
                rendered, tokens = _prepare(client, body)
                sha = store_request(requests_dir, body, rendered, tokens)
                # computed from the two stored prompts alone, before the changed request is sent
                extra = prediction(hyp.rule, THRESHOLD, MARGIN, _ids(base_tokens), _ids(tokens)) if role == "changed" else {}
                start = utc_now()
                response = client.chat(body)
                seq += 1
                rec = {**common, "seq": seq, "repetition": rep, "change": change.id, "role": role, "nonce": nonce,
                       "request_sha256": sha, "ts_start": start, "ts_end": utc_now(),
                       "local_date": datetime.now().strftime("%Y-%m-%d"), "observed": observed(response),
                       "usage_raw": response.get("usage"), "timings_raw": response.get("timings"), **extra}
                append(log, rec)
                records.append(rec)
                base_tokens = tokens if role == "base" else base_tokens
            trial = evaluate_trial(records[-2], records[-1], requests_dir, m2, hid)
            if trial["failures"] or trial["unmeasurable"]:
                halted = True
                break
        if halted:
            break
    report = evaluate(records, requests_dir, m2)
    out = m2.results_dir / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                     newline="\n")
    return report


def probe(m2: M2Config, controls: ControlsConfig, hid: str, changes: list[str], client: Client,
          fixture: Path = FIXTURE) -> dict:
    hyp = m2.hypothesis(hid)
    known = [c.id for c in m2.changes]
    unknown = [c for c in changes if c not in known]
    if unknown:
        raise Refusal(f"unknown change(s) {unknown}; known: {known}")
    props = client.props()
    system_text = (fixture / "system.txt").read_bytes().decode("utf-8")
    tools = json.loads((fixture / "tools.json").read_text(encoding="utf-8"))
    trials = []
    for change in changes:
        nonce = new_nonce(controls.nonce_bytes)
        base_body, changed_body = _bodies(controls, change, system_text, tools, nonce)
        (base_rendered, base_tokens), (changed_rendered, changed_tokens) = _prepare(client, base_body), _prepare(client, changed_body)
        p = prediction(hyp.rule, THRESHOLD, MARGIN, _ids(base_tokens), _ids(changed_tokens))
        first, second = client.chat(base_body), client.chat(changed_body)
        trials.append({"change": change, "reading": m2.change(change).reading, "prompt_tokens": len(changed_tokens),
                       "render_diff": render_diff(base_rendered, changed_rendered), **p,
                       "base": {"observed": observed(first)}, "changed": {"observed": observed(second)},
                       "match": observed(second)["cache_n"] == p["predicted_reuse"]})
    return {"server": _server(props), "hypothesis": hid, "rule": hyp.rule, "slots_required": hyp.slots, "trials": trials}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.m2")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "probe"):
        p = sub.add_parser(name)
        p.add_argument("--url", required=True, help="the server's address, e.g. http://127.0.0.1:8080")
        p.add_argument("--hypothesis", required=True, help="an id registered in config/m2.toml")
    sub.choices["run"].add_argument("--family", required=True)
    sub.choices["run"].add_argument("--model-path", required=True)
    sub.choices["probe"].add_argument("--changes", required=True, help="comma-separated change ids, e.g. S1,S3")
    a = ap.parse_args(argv)
    try:
        m2 = load_m2_config(REPO_ROOT / "config" / "m2.toml", REPO_ROOT)
        controls = load_controls_config(REPO_ROOT / "config" / "controls.toml", REPO_ROOT)
        client = Client(a.url, controls.request_timeout_seconds)
        if a.cmd == "probe":
            print(json.dumps(probe(m2, controls, a.hypothesis, a.changes.split(","), client), indent=2, ensure_ascii=True))
            return 0
        engine = load_engines_config(REPO_ROOT / "config" / "engines.toml")["llamacpp"]
        report = run(m2, controls, engine, a.family, a.hypothesis, client, Path(a.model_path))
    except (Refusal, EngineError, ValueError) as e:
        print(f"M2 REFUSED: {e}".encode("ascii", "backslashreplace").decode("ascii"), file=sys.stderr)
        return 2
    print(render(report).encode("ascii", "backslashreplace").decode("ascii"))
    return 0 if report["outcome"] == "ALL MATCH" else 1


if __name__ == "__main__":
    sys.exit(main())
