"""Idle expiry, run against one engine serving one model, under one hypothesis.

A trial is two requests under one fresh nonce: an anchor, a gap of g seconds in which the driver sends
nothing but one GET /props at the end (at the pinned commit that is not a task: it neither wakes the
server nor moves its idle timer, and it reports `is_sleeping`), then the anchor again byte for byte.
The anchor is rendered and tokenized before it is sent, and nothing is rendered or tokenized until
the resend has been answered: at the pin /apply-template and /tokenize wait for a sleeping server to
reload. The resend's predicted reuse is a function of the registered timer, the registered gap and the
anchor's token count, nothing else. The record carries the prediction and the `is_sleeping` read;
`summarize_m4` states the rule and recomputes every trial from disk. This module sends, waits and
records.

A prediction that is not met is a result, and the run goes on. The run stops when a trial fails a
control or a field is NOT MEASURABLE, because nothing after that can be read.

`run` refuses unless the three configs are registered, the local model file hashes to the configured
digest, the server reports the pinned build, the number of slots the hypothesis requires, and a slot
context; a trial whose anchor does not fit that context is not sent. `probe` runs one trial per gap it
is given, optionally reading /props or rendering at a named second inside each gap, prints what came
back and records nothing. The clock is a parameter so tests can pass one whose time moves only when
the driver sleeps.
"""
import argparse
import json
import sys
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.clock import REAL, Clock
from prefix_mortality.config import (ControlsConfig, EngineConfig, M4Config, load_controls_config,
                                     load_engines_config, load_m4_config)
from prefix_mortality.controls import FIXTURE, Refusal, _gate_local, _gate_server, _server, build_body
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.llamacpp import Client, EngineError, observed
from prefix_mortality.m7 import _gate_context, _gate_slots
from prefix_mortality.nonce import new_nonce
from prefix_mortality.record import SCHEMA_VERSION, append, store_request
from prefix_mortality.summarize_m4 import evaluate, evaluate_trial, prediction, render


def _sleeping(props: dict):
    v = props.get("is_sleeping")
    return v if isinstance(v, bool) else None


def _anchor(controls: ControlsConfig, system_text: str, tools: list, client: Client) -> dict:
    """The base request under a fresh nonce, rendered and tokenized before anything is sent."""
    nonce = new_nonce(controls.nonce_bytes)
    body = build_body(controls, system_text, tools, nonce)
    rendered = client.render(body)
    return {"nonce": nonce, "body": body, "rendered": rendered, "tokens": client.tokenize(rendered)}


def _fixture(fixture: Path) -> tuple[str, list]:
    return ((fixture / "system.txt").read_bytes().decode("utf-8"),
            json.loads((fixture / "tools.json").read_text(encoding="utf-8")))


def run(m4: M4Config, controls: ControlsConfig, engine: EngineConfig, family: str, hid: str, client: Client,
        model_path: Path, repo_root: Path = REPO_ROOT, fixture: Path = FIXTURE, clock: Clock = REAL) -> dict:
    hyp = m4.hypothesis(hid)
    if not m4.registered_by:
        raise Refusal(f"{m4.config_path.name} is UNREGISTERED (registered_by is empty); a ledger entry registers it first")
    _gate_local(controls, engine, family, Path(model_path))
    props = client.props()
    _gate_server(engine, props)
    _gate_slots(hyp, props)
    n_ctx = _gate_context(props)
    system_text, tools = _fixture(fixture)
    requests_dir = repo_root / "corpus" / "requests"
    run_id = f"{clock.now_utc().strftime('%Y%m%dT%H%M%SZ')}-{family}-{hid}"
    log = m4.corpus_dir / f"{run_id}.jsonl"
    if log.exists():
        raise Refusal(f"{log} already exists; a run never appends to another run's records")
    common = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "experiment": "m4", "hypothesis": hid,
              "family": family, "engine_release": engine.release, "engine_commit": engine.commit,
              "model_file": engine.model(family).file, "model_sha256": engine.model(family).sha256,
              "server": _server(props),
              "config_sha256": {"controls": sha256_text_file(controls.config_path),
                                "engines": sha256_text_file(engine.config_path),
                                "m4": sha256_text_file(m4.config_path)}}
    records, seq, halted, why = [], 0, False, ""

    def send(base: dict, body: bytes, role: str, extra: dict) -> dict:
        nonlocal seq
        start = clock.stamp()
        response = client.chat(body)
        seq += 1
        rec = {**base, "seq": seq, "role": role, "ts_start": start, "ts_end": clock.stamp(),
               "local_date": clock.today(), "observed": observed(response),
               "usage_raw": response.get("usage"), "timings_raw": response.get("timings"), **extra}
        append(log, rec)
        records.append(rec)
        return rec

    for rep in range(1, hyp.repetitions + 1):
        for gap in hyp.gaps:
            a = _anchor(controls, system_text, tools, client)
            n = len(a["tokens"])
            if n >= n_ctx:
                # the server would refuse the request; nothing is sent and nothing can be read
                halted, why = True, (f"the anchor ({n} tokens) does not fit the slot context ({n_ctx} tokens); "
                                     "NOT MEASURABLE on this server")
                break
            p = prediction(hyp, gap, n)                        # from the registered values and the stored prompt
            sha = store_request(requests_dir, a["body"], a["rendered"], a["tokens"])
            base = {**common, "repetition": rep, "gap_seconds": gap, "nonce": a["nonce"], "request_sha256": sha}
            send(base, a["body"], "anchor", {"predicted_reuse": 0})
            clock.sleep(gap)                                   # nothing is sent until the read at the end
            gap_probe = {"is_sleeping": _sleeping(client.props()), "ts": clock.stamp()}
            send(base, a["body"], "resend", {**p, "gap_probe": gap_probe})
            trial = evaluate_trial(records[-2], records[-1], requests_dir, m4, hyp)
            if trial["failures"] or trial["unmeasurable"]:
                halted = True
                break
        if halted:
            break
    if not records:
        raise Refusal(why or "no trial was sent")
    report = evaluate(records, requests_dir, m4)
    out = m4.results_dir / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                     newline="\n")
    return report


def probe(m4: M4Config, controls: ControlsConfig, hid: str, family: str, gaps: list[int], client: Client,
          fixture: Path = FIXTURE, clock: Clock = REAL, props_at: int | None = None,
          render_at: int | None = None) -> dict:
    hyp = m4.hypothesis(hid)
    if any(g < 0 for g in gaps):
        raise Refusal(f"a gap is 0 or more seconds, got {gaps}")
    inside = [(at, action) for at, action in ((props_at, "props"), (render_at, "render")) if at is not None]
    for at, action in inside:
        if any(not 0 < at < g for g in gaps):
            raise Refusal(f"{action} at {at} s must fall inside every gap, got gaps {gaps}")
    props = client.props()
    system_text, tools = _fixture(fixture)
    trials = []
    for gap in gaps:
        a = _anchor(controls, system_text, tools, client)
        p = prediction(hyp, gap, len(a["tokens"]))
        t = {"gap_seconds": gap, "anchor_tokens": len(a["tokens"]), **p,
             "anchor_reuse": observed(client.chat(a["body"]))["cache_n"], "in_gap": []}
        waited = 0
        for at, action in sorted(inside):
            clock.sleep(at - waited)
            waited = at
            if action == "render":
                client.render(a["body"])
            t["in_gap"].append({"at": at, "action": action, "is_sleeping": _sleeping(client.props())})
        clock.sleep(gap - waited)
        t["sleeping_after_the_gap"] = _sleeping(client.props())
        t["resend"] = observed(client.chat(a["body"]))
        t["match"] = t["resend"]["cache_n"] == p["predicted_reuse"]
        trials.append(t)
    return {"server": _server(props), "hypothesis": hid, "family": family, "slots_required": hyp.slots,
            "sleep_idle_seconds": hyp.sleep_idle_seconds, "trials": trials}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.m4")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "probe"):
        p = sub.add_parser(name)
        p.add_argument("--url", required=True, help="the server's address, e.g. http://127.0.0.1:8080")
        p.add_argument("--hypothesis", required=True, help="an id registered in config/m4.toml")
        p.add_argument("--family", required=True, help="a family named in config/engines.toml")
    sub.choices["run"].add_argument("--model-path", required=True)
    sub.choices["probe"].add_argument("--gaps", required=True, help="comma-separated gaps in seconds, e.g. 0,30")
    sub.choices["probe"].add_argument("--props-at", type=int, default=None,
                                      help="also read GET /props this many seconds into each gap")
    sub.choices["probe"].add_argument("--render-at", type=int, default=None,
                                      help="POST /apply-template this many seconds into each gap, then read /props")
    a = ap.parse_args(argv)
    try:
        m4 = load_m4_config(REPO_ROOT / "config" / "m4.toml", REPO_ROOT)
        controls = load_controls_config(REPO_ROOT / "config" / "controls.toml", REPO_ROOT)
        client = Client(a.url, controls.request_timeout_seconds)
        if a.cmd == "probe":
            gaps = [int(x) for x in a.gaps.split(",")]
            out = probe(m4, controls, a.hypothesis, a.family, gaps, client, props_at=a.props_at, render_at=a.render_at)
            print(json.dumps(out, indent=2, ensure_ascii=True))
            return 0
        engine = load_engines_config(REPO_ROOT / "config" / "engines.toml")["llamacpp"]
        report = run(m4, controls, engine, a.family, a.hypothesis, client, Path(a.model_path))
    except (Refusal, EngineError, ValueError) as e:
        print(f"M4 REFUSED: {e}".encode("ascii", "backslashreplace").decode("ascii"), file=sys.stderr)
        return 2
    print(render(report).encode("ascii", "backslashreplace").decode("ascii"))
    return 0 if report["outcome"] == "ALL MATCH" else 1


if __name__ == "__main__":
    sys.exit(main())
