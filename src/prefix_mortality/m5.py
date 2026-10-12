"""Rebuild, run against one engine serving one model, under one hypothesis.

A trial is two requests under one fresh nonce: a recorded conversation replayed in full at its last
assistant turn, then the same conversation compacted at its midpoint — the messages from the first
user message up to the cut removed (`trim`) or replaced by one registered summary message
(`summary`). Both are rendered, tokenized and stored before either is sent; the compacted request's
predicted reuse is a function of the two stored token lists and the registered constants under the
hypothesis's rule, nothing else. The record carries the prediction, with the cache-reuse walk's chunk
list; `summarize_m5` states the rules and recomputes every trial from disk. This module sends and
records.

A prediction that is not met is a result, and the run goes on. The run stops when a trial fails a
control or a field is NOT MEASURABLE, because nothing after that can be read.

`run` refuses unless the three configs are registered, the local model file hashes to the configured
digest, the server reports the pinned build, the number of slots the hypothesis requires, and a slot
context; a trial whose requests do not fit that context is not sent. The server does not report
`--cache-reuse`: the run script passes it, and the records read it back only through the walk's
result. `probe` runs the trials of named conversations, prints what came back and records nothing.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import (ControlsConfig, EngineConfig, M5Config, load_controls_config, load_engines_config,
                                     load_m5_config)
from prefix_mortality.controls import FIXTURE, Refusal, _gate_local, _gate_server, _server
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.llamacpp import Client, EngineError, observed
from prefix_mortality.m7 import _gate_context, _gate_slots
from prefix_mortality.nonce import new_nonce
from prefix_mortality.record import SCHEMA_VERSION, append, store_request, utc_now
from prefix_mortality.recorded import SIMULATIONS, load as load_recorded
from prefix_mortality.replay import body_at, compacted, last_turn, longest, midpoint_cut
from prefix_mortality.slotsim import tokens
from prefix_mortality.summarize_m5 import evaluate, evaluate_trial, prediction, render
from prefix_mortality.summarize_m8 import generated_text


def _fixture(fixture: Path) -> tuple[str, list]:
    return ((fixture / "system.txt").read_bytes().decode("utf-8"),
            json.loads((fixture / "tools.json").read_text(encoding="utf-8")))


def _prepare(client: Client, body: bytes) -> dict:
    rendered = client.render(body)
    toks = client.tokenize(rendered)
    return {"body": body, "rendered": rendered, "tokens": toks,
            "list": tokens([t["id"] for t in toks], [t["piece"] for t in toks])}


def _trial(m5: M5Config, controls: ControlsConfig, system_text: str, tools: list, sim: dict, arm: str,
           kwargs: dict | None, client: Client) -> dict:
    """The two requests of one trial, rendered and tokenized, before either is sent."""
    nonce = new_nonce(controls.nonce_bytes)
    system = f"run {nonce}\n{system_text}"
    t, cut = last_turn(sim), midpoint_cut(sim)
    comp_sim, t2 = compacted(sim, t, cut, m5.summary if arm == "summary" else None)
    full = _prepare(client, body_at(controls, system, tools, sim, t, template_kwargs=kwargs))
    comp = _prepare(client, body_at(controls, system, tools, comp_sim, t2, template_kwargs=kwargs))
    return {"nonce": nonce, "turn_index": t, "cut_index": cut, "compacted_turn_index": t2,
            "full": full, "compacted": comp}


def run(m5: M5Config, controls: ControlsConfig, engine: EngineConfig, family: str, hid: str, client: Client,
        model_path: Path, repo_root: Path = REPO_ROOT, fixture: Path = FIXTURE) -> dict:
    hyp = m5.hypothesis(hid)
    if not m5.registered_by:
        raise Refusal(f"{m5.config_path.name} is UNREGISTERED (registered_by is empty); a ledger entry registers it first")
    kwargs = m5.kwargs(family)
    _gate_local(controls, engine, family, Path(model_path))
    props = client.props()
    _gate_server(engine, props)
    _gate_slots(hyp, props)
    n_ctx = _gate_context(props)
    sims, prov = load_recorded(m5.recorded_dir)
    chosen = longest(sims, m5.conversations)
    system_text, tools = _fixture(fixture)
    requests_dir = repo_root / "corpus" / "requests"
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{family}-{hid}"
    log = m5.corpus_dir / f"{run_id}.jsonl"
    if log.exists():
        raise Refusal(f"{log} already exists; a run never appends to another run's records")
    common = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "experiment": "m5", "hypothesis": hid,
              "family": family, "engine_release": engine.release, "engine_commit": engine.commit,
              "model_file": engine.model(family).file, "model_sha256": engine.model(family).sha256,
              "server": _server(props), "recorded_dir": m5.recorded_dir.name,
              "recorded_sha256": prov["output"][SIMULATIONS]["sha256"],
              "config_sha256": {"controls": sha256_text_file(controls.config_path),
                                "engines": sha256_text_file(engine.config_path),
                                "m5": sha256_text_file(m5.config_path)}}
    records, seq, halted, why = [], 0, False, ""
    for sim in chosen:
        for arm in m5.arms:
            tr = _trial(m5, controls, system_text, tools, sim, arm, kwargs, client)
            too_big = [role for role in ("full", "compacted") if len(tr[role]["list"]) >= n_ctx]
            if too_big:
                # the server would refuse the request; nothing is sent and nothing can be read
                halted, why = True, (f"conversation {sim['task_id']} arm {arm}: the {' and '.join(too_big)} request does "
                                     f"not fit the slot context ({n_ctx} tokens); NOT MEASURABLE on this server")
                break
            p = prediction(m5, hid, tr["full"]["list"], tr["compacted"]["list"])   # before anything is sent
            for role, turn in (("full", tr["turn_index"]), ("compacted", tr["compacted_turn_index"])):
                req = tr[role]
                sha = store_request(requests_dir, req["body"], req["rendered"], req["tokens"])
                start = utc_now()
                response = client.chat(req["body"])
                seq += 1
                rec = {**common, "seq": seq, "conversation": sim["task_id"], "arm": arm, "role": role,
                       "nonce": tr["nonce"], "turn_index": turn, "cut_index": tr["cut_index"], "request_sha256": sha,
                       "ts_start": start, "ts_end": utc_now(), "local_date": datetime.now().strftime("%Y-%m-%d"),
                       "generated": generated_text(response), "observed": observed(response),
                       "usage_raw": response.get("usage"), "timings_raw": response.get("timings"),
                       **(p if role == "compacted" else {})}
                append(log, rec)
                records.append(rec)
            trial = evaluate_trial(records[-2], records[-1], requests_dir, m5, hid)
            if trial["failures"] or trial["unmeasurable"]:
                halted = True
                break
        if halted:
            break
    if not records:
        raise Refusal(why or "no trial was sent")
    report = evaluate(records, requests_dir, m5)
    out = m5.results_dir / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                     newline="\n")
    return report


def probe(m5: M5Config, controls: ControlsConfig, hid: str, family: str, task_ids: list[str], client: Client,
          fixture: Path = FIXTURE) -> dict:
    hyp = m5.hypothesis(hid)
    kwargs = m5.kwargs(family)
    props = client.props()
    sims, _ = load_recorded(m5.recorded_dir)
    by_task = {s["task_id"]: s for s in sims}
    missing = [t for t in task_ids if t not in by_task]
    if missing:
        raise Refusal(f"no recorded conversation with task id {missing}")
    system_text, tools = _fixture(fixture)
    out = []
    for task_id in task_ids:
        for arm in m5.arms:
            tr = _trial(m5, controls, system_text, tools, by_task[task_id], arm, kwargs, client)
            p = prediction(m5, hid, tr["full"]["list"], tr["compacted"]["list"])
            first = observed(client.chat(tr["full"]["body"]))
            second = observed(client.chat(tr["compacted"]["body"]))
            out.append({"conversation": task_id, "arm": arm, "n_full": len(tr["full"]["list"]),
                        "n_compacted": len(tr["compacted"]["list"]), **p, "full": first, "compacted": second,
                        "match": second["cache_n"] == p["predicted_reuse"]})
    return {"server": _server(props), "hypothesis": hid, "family": family, "slots_required": hyp.slots,
            "rule": hyp.rule, "trials": out}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.m5")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "probe"):
        p = sub.add_parser(name)
        p.add_argument("--url", required=True, help="the server's address, e.g. http://127.0.0.1:8080")
        p.add_argument("--hypothesis", required=True, help="an id registered in config/m5.toml")
        p.add_argument("--family", required=True, help="a family named in config/engines.toml and config/m5.toml")
    sub.choices["run"].add_argument("--model-path", required=True)
    sub.choices["probe"].add_argument("--task-ids", required=True, help="comma-separated task ids, e.g. 12,18")
    a = ap.parse_args(argv)
    try:
        m5 = load_m5_config(REPO_ROOT / "config" / "m5.toml", REPO_ROOT)
        controls = load_controls_config(REPO_ROOT / "config" / "controls.toml", REPO_ROOT)
        client = Client(a.url, controls.request_timeout_seconds)
        if a.cmd == "probe":
            print(json.dumps(probe(m5, controls, a.hypothesis, a.family, a.task_ids.split(","), client), indent=2,
                             ensure_ascii=True))
            return 0
        engine = load_engines_config(REPO_ROOT / "config" / "engines.toml")["llamacpp"]
        report = run(m5, controls, engine, a.family, a.hypothesis, client, Path(a.model_path))
    except (Refusal, EngineError, ValueError) as e:
        print(f"M5 REFUSED: {e}".encode("ascii", "backslashreplace").decode("ascii"), file=sys.stderr)
        return 2
    print(render(report).encode("ascii", "backslashreplace").decode("ascii"))
    return 0 if report["outcome"] == "ALL MATCH" else 1


if __name__ == "__main__":
    sys.exit(main())
