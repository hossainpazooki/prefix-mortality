"""Eviction by intervening requests, run against one engine serving one model, under one hypothesis.

A trial is K + 2 requests under K + 1 fresh nonces: an anchor, K foreign requests served one at a
time, then the anchor again byte for byte. Every request of a trial is rendered, tokenized and stored
before the first is sent, and the resend's predicted reuse is a function of the stored token counts,
the registered KV geometry and the registered cache size, nothing else. The record carries the
prediction; `summarize_m7` states the rule and recomputes every trial from disk. This module sends
and records.

A prediction that is not met is a result, and the run goes on. The run stops when a trial fails a
control or a field is NOT MEASURABLE, because nothing after that can be read.

`run` refuses unless the three configs are registered, the local model file hashes to the configured
digest, the server reports the pinned build, the number of slots the hypothesis requires, and a slot
context; a trial whose anchor does not fit that context is not sent, because the server would refuse
it and nothing could be read. `probe` runs one trial per K it is given, prints what came back and
records nothing.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import (ControlsConfig, EngineConfig, M7Config, M7Hypothesis, load_controls_config,
                                     load_engines_config, load_m7_config)
from prefix_mortality.controls import FIXTURE, Refusal, _gate_local, _gate_server, _server, build_body
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.llamacpp import Client, EngineError, observed
from prefix_mortality.nonce import new_nonce
from prefix_mortality.record import SCHEMA_VERSION, append, store_request, utc_now
from prefix_mortality.summarize_m7 import evaluate, evaluate_trial, prediction, render


def _gate_slots(hyp: M7Hypothesis, props: dict) -> None:
    slots = props.get("total_slots")
    if slots != hyp.slots:
        raise Refusal(f"{hyp.id} requires a server reporting {hyp.slots} slot(s); this one reports {slots!r}")


def _gate_context(props: dict) -> int:
    n_ctx = _server(props).get("n_ctx")
    if isinstance(n_ctx, bool) or not isinstance(n_ctx, int) or n_ctx <= 0:
        raise Refusal(f"the server reports no slot context (default_generation_settings.n_ctx is {n_ctx!r}); "
                      "whether a prompt fits cannot be known")
    return n_ctx


def _prepare(client: Client, body: bytes) -> tuple[str, list[dict]]:
    rendered = client.render(body)
    return rendered, client.tokenize(rendered)


def _request(controls: ControlsConfig, system_text: str, tools: list, role: str, index, client: Client) -> dict:
    nonce = new_nonce(controls.nonce_bytes)
    body = build_body(controls, system_text, tools, nonce)
    rendered, tokens = _prepare(client, body)
    return {"role": role, "index": index, "nonce": nonce, "body": body, "rendered": rendered, "tokens": tokens}


def _trial(controls: ControlsConfig, system_text: str, tools: list, k: int, client: Client) -> list[dict]:
    """The K + 2 requests of one trial, rendered and tokenized, before any is sent. The resend is the
    anchor's bytes under the anchor's nonce."""
    anchor = _request(controls, system_text, tools, "anchor", None, client)
    foreign = [_request(controls, system_text, tools, "foreign", i, client) for i in range(1, k + 1)]
    return [anchor, *foreign, {**anchor, "role": "resend"}]


def _predict(m7: M7Config, family: str, reqs: list[dict]) -> dict:
    return prediction(m7, family, len(reqs[0]["tokens"]), [len(r["tokens"]) for r in reqs[1:-1]])


def run(m7: M7Config, controls: ControlsConfig, engine: EngineConfig, family: str, hid: str, client: Client,
        model_path: Path, repo_root: Path = REPO_ROOT, fixture: Path = FIXTURE) -> dict:
    hyp = m7.hypothesis(hid)
    m7.geometry(family)
    if not m7.registered_by:
        raise Refusal(f"{m7.config_path.name} is UNREGISTERED (registered_by is empty); a ledger entry registers it first")
    _gate_local(controls, engine, family, Path(model_path))
    props = client.props()
    _gate_server(engine, props)
    _gate_slots(hyp, props)
    n_ctx = _gate_context(props)
    system_text = (fixture / "system.txt").read_bytes().decode("utf-8")
    tools = json.loads((fixture / "tools.json").read_text(encoding="utf-8"))
    requests_dir = repo_root / "corpus" / "requests"
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{family}-{hid}"
    log = m7.corpus_dir / f"{run_id}.jsonl"
    if log.exists():
        raise Refusal(f"{log} already exists; a run never appends to another run's records")
    common = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "experiment": "m7", "hypothesis": hid,
              "family": family, "engine_release": engine.release, "engine_commit": engine.commit,
              "model_file": engine.model(family).file, "model_sha256": engine.model(family).sha256,
              "server": _server(props),
              "config_sha256": {"controls": sha256_text_file(controls.config_path),
                                "engines": sha256_text_file(engine.config_path),
                                "m7": sha256_text_file(m7.config_path)}}
    records, seq, halted, why = [], 0, False, ""
    for rep in range(1, m7.repetitions + 1):
        for k in m7.k_schedule:
            reqs = _trial(controls, system_text, tools, k, client)
            n_anchor = len(reqs[0]["tokens"])
            if n_anchor >= n_ctx:
                # the server would refuse the request; nothing is sent and nothing can be read
                halted, why = True, (f"the anchor ({n_anchor} tokens) does not fit the slot context "
                                     f"({n_ctx} tokens); NOT MEASURABLE on this server")
                break
            p = _predict(m7, family, reqs)                # from the stored prompts alone, before anything is sent
            for r in reqs:
                sha = store_request(requests_dir, r["body"], r["rendered"], r["tokens"])
                extra = p if r["role"] == "resend" else {"predicted_reuse": 0}
                start = utc_now()
                response = client.chat(r["body"])
                seq += 1
                rec = {**common, "seq": seq, "repetition": rep, "k": k, "role": r["role"], "index": r["index"],
                       "nonce": r["nonce"], "request_sha256": sha, "ts_start": start, "ts_end": utc_now(),
                       "local_date": datetime.now().strftime("%Y-%m-%d"), "observed": observed(response),
                       "usage_raw": response.get("usage"), "timings_raw": response.get("timings"), **extra}
                append(log, rec)
                records.append(rec)
            trial = evaluate_trial(records[-(k + 2)], records[len(records) - k - 1:-1], records[-1], requests_dir, m7)
            if trial["failures"] or trial["unmeasurable"]:
                halted = True
                break
        if halted:
            break
    if not records:
        raise Refusal(why or "no trial was sent")
    report = evaluate(records, requests_dir, m7)
    out = m7.results_dir / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                     newline="\n")
    return report


def probe(m7: M7Config, controls: ControlsConfig, hid: str, family: str, ks: list[int], client: Client,
          fixture: Path = FIXTURE) -> dict:
    hyp = m7.hypothesis(hid)
    m7.geometry(family)
    if any(k < 0 for k in ks):
        raise Refusal(f"K must be 0 or more, got {ks}")
    props = client.props()
    system_text = (fixture / "system.txt").read_bytes().decode("utf-8")
    tools = json.loads((fixture / "tools.json").read_text(encoding="utf-8"))
    trials = []
    for k in ks:
        reqs = _trial(controls, system_text, tools, k, client)
        p = _predict(m7, family, reqs)
        got = [observed(client.chat(r["body"])) for r in reqs]
        trials.append({"k": k, "anchor_tokens": len(reqs[0]["tokens"]), **p,
                       "anchor_reuse": got[0]["cache_n"], "foreign_reuse": [g["cache_n"] for g in got[1:-1]],
                       "resend": got[-1], "match": got[-1]["cache_n"] == p["predicted_reuse"]})
    return {"server": _server(props), "hypothesis": hid, "family": family, "slots_required": hyp.slots,
            "cache_ram_mib": m7.cache_ram_mib, "bytes_per_token": m7.bytes_per_token(family), "trials": trials}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.m7")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "probe"):
        p = sub.add_parser(name)
        p.add_argument("--url", required=True, help="the server's address, e.g. http://127.0.0.1:8080")
        p.add_argument("--hypothesis", required=True, help="an id registered in config/m7.toml")
        p.add_argument("--family", required=True, help="a family named in config/engines.toml and config/m7.toml")
    sub.choices["run"].add_argument("--model-path", required=True)
    sub.choices["probe"].add_argument("--ks", required=True, help="comma-separated K values, e.g. 1,12")
    a = ap.parse_args(argv)
    try:
        m7 = load_m7_config(REPO_ROOT / "config" / "m7.toml", REPO_ROOT)
        controls = load_controls_config(REPO_ROOT / "config" / "controls.toml", REPO_ROOT)
        client = Client(a.url, controls.request_timeout_seconds)
        if a.cmd == "probe":
            ks = [int(x) for x in a.ks.split(",")]
            print(json.dumps(probe(m7, controls, a.hypothesis, a.family, ks, client), indent=2, ensure_ascii=True))
            return 0
        engine = load_engines_config(REPO_ROOT / "config" / "engines.toml")["llamacpp"]
        report = run(m7, controls, engine, a.family, a.hypothesis, client, Path(a.model_path))
    except (Refusal, EngineError, ValueError) as e:
        print(f"M7 REFUSED: {e}".encode("ascii", "backslashreplace").decode("ascii"), file=sys.stderr)
        return 2
    print(render(report).encode("ascii", "backslashreplace").decode("ascii"))
    return 0 if report["outcome"] == "ALL MATCH" else 1


if __name__ == "__main__":
    sys.exit(main())
