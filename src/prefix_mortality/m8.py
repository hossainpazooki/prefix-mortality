"""Lifespan on recorded runs, run against one engine serving one model, under one hypothesis.

A run replays recorded conversations (`prefix_mortality.recorded`, `replay`) one request per assistant
turn, with no nonce. C = 1 sends every conversation one after another in file order; C > 1 sends the C
conversations with the most assistant turns in round robin. Each request is rendered, tokenized and
stored before it is sent; its predicted reuse is the pinned server's slot and prompt-cache policy
(`slotsim`) applied to the stored token lists sent so far, nothing else. The record carries the
prediction and the text of the one token generated; `summarize_m8` states the
rules and recomputes every request from disk. This module sends and records.

A prediction that is not met is a result, and the run goes on. The run stops when a request fails a
control or a field is NOT MEASURABLE, because nothing after that can be read.

`run` refuses unless the three configs are registered, the local model file hashes to the configured
digest, the server reports the pinned build, the number of slots the hypothesis requires, and a slot
context; a request that does not fit that context is not sent, and the run stops there. `probe`
replays named conversations for a few turns, prints what came back against the prediction and records
nothing.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import (ControlsConfig, EngineConfig, M8Config, load_controls_config, load_engines_config,
                                     load_m8_config)
from prefix_mortality.controls import FIXTURE, Refusal, _gate_local, _gate_server, _server
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.llamacpp import Client, EngineError, observed
from prefix_mortality.m7 import _gate_context, _gate_slots
from prefix_mortality.record import SCHEMA_VERSION, append, store_request, utc_now
from prefix_mortality.recorded import SIMULATIONS, load as load_recorded
from prefix_mortality.replay import assistant_turns, body_at
from prefix_mortality.slotsim import tokens
from prefix_mortality.summarize_m8 import (evaluate, evaluate_request, generated_text, make_sim, prediction_fields,
                                           render, schedule)


def _fixture(fixture: Path) -> tuple[str, list]:
    return ((fixture / "system.txt").read_bytes().decode("utf-8"),
            json.loads((fixture / "tools.json").read_text(encoding="utf-8")))


def _prepare(client: Client, body: bytes) -> tuple[str, list[dict], list]:
    rendered = client.render(body)
    toks = client.tokenize(rendered)
    return rendered, toks, tokens([t["id"] for t in toks], [t["piece"] for t in toks])


def run(m8: M8Config, controls: ControlsConfig, engine: EngineConfig, family: str, hid: str, c: int, client: Client,
        model_path: Path, repo_root: Path = REPO_ROOT, fixture: Path = FIXTURE) -> dict:
    hyp = m8.hypothesis(hid)
    if not m8.registered_by:
        raise Refusal(f"{m8.config_path.name} is UNREGISTERED (registered_by is empty); a ledger entry registers it first")
    if c not in hyp.interleave:
        raise Refusal(f"{hid} registers C in {list(hyp.interleave)}; got {c}")
    m8.geometry(family)
    kwargs = m8.kwargs(family)
    _gate_local(controls, engine, family, Path(model_path))
    props = client.props()
    _gate_server(engine, props)
    _gate_slots(hyp, props)
    n_ctx = _gate_context(props)
    sims, prov = load_recorded(m8.recorded_dir)
    plan = schedule(sims, c)
    by_task = {s["task_id"]: s for s in sims}
    system_text, tools = _fixture(fixture)
    requests_dir = repo_root / "corpus" / "requests"
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{family}-{hid}-c{c}"
    log = m8.corpus_dir / f"{run_id}.jsonl"
    if log.exists():
        raise Refusal(f"{log} already exists; a run never appends to another run's records")
    common = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "experiment": "m8", "hypothesis": hid,
              "family": family, "c": c, "engine_release": engine.release, "engine_commit": engine.commit,
              "model_file": engine.model(family).file, "model_sha256": engine.model(family).sha256,
              "server": _server(props), "recorded_dir": m8.recorded_dir.name,
              "recorded_sha256": prov["output"][SIMULATIONS]["sha256"],
              "config_sha256": {"controls": sha256_text_file(controls.config_path),
                                "engines": sha256_text_file(engine.config_path),
                                "m8": sha256_text_file(m8.config_path)}}
    sim = make_sim(m8, hyp, family)
    records, seq, why = [], 0, ""
    for task_id, turn_index, turn_number in plan:
        body = body_at(controls, system_text, tools, by_task[task_id], turn_index, template_kwargs=kwargs)
        rendered, toks, tl = _prepare(client, body)
        if len(tl) >= n_ctx:
            # the server would refuse the request; nothing is sent and nothing after it can be read
            why = (f"request {seq + 1} ({task_id} turn {turn_number}, {len(tl)} tokens) does not fit the slot "
                   f"context ({n_ctx} tokens); NOT MEASURABLE on this server")
            break
        p = prediction_fields(sim.predict(tl))               # from the stored tokens alone, before the send
        sha = store_request(requests_dir, body, rendered, toks)
        start = utc_now()
        response = client.chat(body)
        seq += 1
        gen = generated_text(response)
        rec = {**common, "seq": seq, "conversation": task_id, "turn_index": turn_index, "turn_number": turn_number,
               "request_sha256": sha, "ts_start": start, "ts_end": utc_now(),
               "local_date": datetime.now().strftime("%Y-%m-%d"), "generated": gen, "observed": observed(response),
               "usage_raw": response.get("usage"), "timings_raw": response.get("timings"), **p}
        append(log, rec)
        records.append(rec)
        sim.commit(tl)
        row = evaluate_request(rec, tl, n_ctx)
        if row["failures"] or row["unmeasurable"]:
            break
    if not records:
        raise Refusal(why or "no request was sent")
    report = evaluate(records, requests_dir, m8)
    out = m8.results_dir / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                     newline="\n")
    return report


def probe(m8: M8Config, controls: ControlsConfig, hid: str, family: str, task_ids: list[str], turns: int,
          client: Client, fixture: Path = FIXTURE) -> dict:
    hyp = m8.hypothesis(hid)
    kwargs = m8.kwargs(family)
    props = client.props()
    sims, _ = load_recorded(m8.recorded_dir)
    by_task = {s["task_id"]: s for s in sims}
    missing = [t for t in task_ids if t not in by_task]
    if missing:
        raise Refusal(f"no recorded conversation with task id {missing}")
    system_text, tools = _fixture(fixture)
    sim = make_sim(m8, hyp, family)
    out = []
    for i in range(turns):
        for task_id in task_ids:
            at = assistant_turns(by_task[task_id])
            if i >= len(at):
                continue
            body = body_at(controls, system_text, tools, by_task[task_id], at[i], template_kwargs=kwargs)
            _, _, tl = _prepare(client, body)
            p = prediction_fields(sim.predict(tl))
            response = client.chat(body)
            gen = generated_text(response)
            o = observed(response)
            sim.commit(tl)
            out.append({"conversation": task_id, "turn": i + 1, "n": len(tl), **p, "generated": gen, "observed": o,
                        "match": o["cache_n"] == p["predicted_reuse"]})
    return {"server": _server(props), "hypothesis": hid, "family": family, "slots_required": hyp.slots,
            "requests": out}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.m8")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "probe"):
        p = sub.add_parser(name)
        p.add_argument("--url", required=True, help="the server's address, e.g. http://127.0.0.1:8080")
        p.add_argument("--hypothesis", required=True, help="an id registered in config/m8.toml")
        p.add_argument("--family", required=True, help="a family named in config/engines.toml and config/m8.toml")
    sub.choices["run"].add_argument("--model-path", required=True)
    sub.choices["run"].add_argument("--c", type=int, required=True, help="conversations in round robin; 1 = one after another")
    sub.choices["probe"].add_argument("--task-ids", required=True, help="comma-separated task ids, e.g. 12,18")
    sub.choices["probe"].add_argument("--turns", type=int, default=4, help="assistant turns to replay per conversation")
    a = ap.parse_args(argv)
    try:
        m8 = load_m8_config(REPO_ROOT / "config" / "m8.toml", REPO_ROOT)
        controls = load_controls_config(REPO_ROOT / "config" / "controls.toml", REPO_ROOT)
        client = Client(a.url, controls.request_timeout_seconds)
        if a.cmd == "probe":
            out = probe(m8, controls, a.hypothesis, a.family, a.task_ids.split(","), a.turns, client)
            print(json.dumps(out, indent=2, ensure_ascii=True))
            return 0
        engine = load_engines_config(REPO_ROOT / "config" / "engines.toml")["llamacpp"]
        report = run(m8, controls, engine, a.family, a.hypothesis, a.c, client, Path(a.model_path))
    except (Refusal, EngineError, ValueError) as e:
        print(f"M8 REFUSED: {e}".encode("ascii", "backslashreplace").decode("ascii"), file=sys.stderr)
        return 2
    print(render(report).encode("ascii", "backslashreplace").decode("ascii"))
    return 0 if report["outcome"] == "ALL MATCH" else 1


if __name__ == "__main__":
    sys.exit(main())
