"""Model switch and restart, run against one family's model as child A, under one hypothesis.

The subject is the process, so this driver starts and stops the server through a `ServerHandle`
(`procs.Subprocess`, built from the run script's command line; the tests pass a stand-in). Router
cells start one router serving child A (the family under test) and child B (the small model pinned in
config/m6.toml); a trial sends the base request to A, its messages to B, and the anchor's bytes to A
again, reading the loaded set the router reports before each request. The restart cell starts a single
server; a trial sends the anchor, stops and starts the process, and resends — once bare, once with the
slot saved to disk before the stop and restored after. Every request is rendered, tokenized and stored
before it is sent, through the same server (the router forwards `/apply-template` and `/tokenize` to
the child the body names); the resend's prediction is a function of the cell and the anchor's token
count. `summarize_m6` states the rules and recomputes every trial from disk. This module sends,
restarts and records.

A prediction that is not met is a result, and the run goes on. The run stops when a trial fails a
control or a field is NOT MEASURABLE. `run` refuses unless the three configs are registered, both model
files hash to their pins, child A reports the pinned build, the slots the hypothesis requires and a slot
context. The records carry what the handle reports about the process (a generation number, a pid, a
start time) and never the command line. `probe` runs one trial of a cell, prints it and records nothing.
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import (ControlsConfig, EngineConfig, M6Config, load_controls_config, load_engines_config,
                                     load_m6_config)
from prefix_mortality.controls import FIXTURE, Refusal, _gate_local, _gate_server, _server
from prefix_mortality.hashing import sha256_file_bytes, sha256_text_file
from prefix_mortality.llamacpp import Client, EngineError, observed
from prefix_mortality.m7 import _gate_context, _gate_slots
from prefix_mortality.nonce import new_nonce
from prefix_mortality.procs import ServerHandle, Subprocess
from prefix_mortality.record import SCHEMA_VERSION, append, body_bytes, store_request, utc_now
from prefix_mortality.summarize_m6 import evaluate, evaluate_trial, prediction, render
from prefix_mortality.summarize_m8 import generated_text


def build_body(cfg: ControlsConfig, system_text: str, tools: list, nonce: str, model: str) -> bytes:
    return body_bytes({"model": model,
                       "messages": [{"role": "system", "content": f"run {nonce}\n{system_text}"},
                                    {"role": "user", "content": cfg.user_message}],
                       "tools": tools, "max_tokens": cfg.max_tokens, "temperature": cfg.temperature,
                       "stream": False})


def _fixture(fixture: Path) -> tuple[str, list]:
    return ((fixture / "system.txt").read_bytes().decode("utf-8"),
            json.loads((fixture / "tools.json").read_text(encoding="utf-8")))


def _statuses(client: Client) -> dict[str, str]:
    """Each child's status as the router reports it in GET /models (`status.value`)."""
    out = client._call("/models", None)
    statuses = {}
    for m in out.get("data") or []:
        status = m.get("status")
        value = status.get("value") if isinstance(status, dict) else status
        if isinstance(m.get("id"), str):
            statuses[m["id"]] = value
    return statuses


def _loaded(client: Client) -> list[str]:
    """The children the router reports loaded."""
    return sorted(n for n, v in _statuses(client).items() if v == "loaded")


def _child_props(client: Client, name: str | None) -> dict:
    return client._call(f"/props?model={name}" if name else "/props", None)


def _load(client: Client, name: str, timeout_seconds: float = 300.0) -> None:
    """POST /models/load, then wait: the router loads a child asynchronously and reports it `loading`
    until its process answers."""
    statuses = _statuses(client)
    if name not in statuses:
        raise Refusal(f"the router knows no model {name!r}; it lists {sorted(statuses)}")
    if statuses[name] != "loaded":
        client._call("/models/load", json.dumps({"model": name}).encode("utf-8"))
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        value = _statuses(client).get(name)
        if value == "loaded":
            return
        if value not in ("loading", "unloaded", "downloaded"):
            raise Refusal(f"the router reports {name!r} as {value!r}")
        time.sleep(1.0)
    raise Refusal(f"the router did not load {name!r} within {timeout_seconds} s")


class _Run:
    """What one run accumulates: the log, the records, the sequence number."""

    def __init__(self, log: Path, common: dict, requests_dir: Path):
        self.log, self.common, self.requests_dir = log, common, requests_dir
        self.records, self.seq = [], 0

    def send(self, client: Client, body: bytes, rendered: str, toks: list[dict], fields: dict) -> dict:
        sha = store_request(self.requests_dir, body, rendered, toks)
        start = utc_now()
        response = client.chat(body)
        self.seq += 1
        rec = {**self.common, "seq": self.seq, "request_sha256": sha, "ts_start": start, "ts_end": utc_now(),
               "local_date": datetime.now().strftime("%Y-%m-%d"), "generated": generated_text(response),
               "response_model": response.get("model"), "observed": observed(response),
               "usage_raw": response.get("usage"), "timings_raw": response.get("timings"), **fields}
        append(self.log, rec)
        self.records.append(rec)
        return rec


def _prepare(client: Client, body: bytes, model: str | None) -> tuple[str, list[dict]]:
    rendered = client.render(body)
    return rendered, client.tokenize(rendered, model=model)


def run(m6: M6Config, controls: ControlsConfig, engine: EngineConfig, family: str, hid: str, handle: ServerHandle,
        model_path: Path, child_b_path: Path | None, repo_root: Path = REPO_ROOT, fixture: Path = FIXTURE) -> dict:
    hyp = m6.hypothesis(hid)
    if not m6.registered_by:
        raise Refusal(f"{m6.config_path.name} is UNREGISTERED (registered_by is empty); a ledger entry registers it first")
    _gate_local(controls, engine, family, Path(model_path))
    child_b = m6.child_b.family
    if hyp.mode == "router":
        if child_b_path is None or not Path(child_b_path).is_file():
            raise Refusal(f"child B's model file {child_b_path} does not exist")
        digest = sha256_file_bytes(Path(child_b_path))
        if digest != m6.child_b.sha256:
            raise Refusal(f"{child_b_path} hashes to {digest}, config pins {m6.child_b.sha256} for {m6.child_b.file}")
    system_text, tools = _fixture(fixture)
    requests_dir = repo_root / "corpus" / "requests"
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{family}-{hid}"
    log = m6.corpus_dir / f"{run_id}.jsonl"
    if log.exists():
        raise Refusal(f"{log} already exists; a run never appends to another run's records")
    handle.start()
    try:
        client = Client(handle.url, controls.request_timeout_seconds)
        model_a = family if hyp.mode == "router" else None
        if hyp.mode == "router":
            _load(client, family)
            if hyp.models_max > 1:
                _load(client, child_b)
        props_a = _child_props(client, model_a)
        _gate_server(engine, props_a)
        _gate_slots(hyp, props_a)
        n_ctx = _gate_context(props_a)
        common = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "experiment": "m6", "hypothesis": hid,
                  "family": family, "mode": hyp.mode, "models_max": hyp.models_max,
                  "engine_release": engine.release, "engine_commit": engine.commit,
                  "model_file": engine.model(family).file, "model_sha256": engine.model(family).sha256,
                  "child_b": {"name": child_b, "file": m6.child_b.file, "sha256": m6.child_b.sha256},
                  "config_sha256": {"controls": sha256_text_file(controls.config_path),
                                    "engines": sha256_text_file(engine.config_path),
                                    "m6": sha256_text_file(m6.config_path)}}
        st = _Run(log, common, requests_dir)
        halted, why = False, ""
        for rep in range(1, m6.repetitions + 1):
            if hyp.mode == "router":
                trial = _router_trial(st, client, controls, system_text, tools, hyp, family, child_b, rep, n_ctx)
            else:
                trial = _restart_trials(st, client, handle, controls, engine, system_text, tools, hyp, family, rep, n_ctx, run_id)
            if trial is None:
                halted, why = True, f"a request of repetition {rep} does not fit the slot context ({n_ctx} tokens); NOT MEASURABLE"
                break
            if trial["failures"] or trial["unmeasurable"]:
                halted = True
                break
    finally:
        handle.stop()
    if not st.records:
        raise Refusal(why or "no trial was sent")
    report = evaluate(st.records, requests_dir, m6)
    out = m6.results_dir / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                     newline="\n")
    return report


def _router_trial(st, client, controls, system_text, tools, hyp, family, child_b, rep, n_ctx):
    nonce = new_nonce(controls.nonce_bytes)
    body_a = build_body(controls, system_text, tools, nonce, family)
    body_b = build_body(controls, system_text, tools, nonce, child_b)
    ra, ta = _prepare(client, body_a, family)
    rb, tb = _prepare(client, body_b, child_b)
    if len(ta) >= n_ctx:
        return None
    p = prediction(hyp, None, len(ta))
    base = {"repetition": rep, "nonce": nonce}
    plan = (("anchor", family, body_a, ra, ta, {}), ("other", child_b, body_b, rb, tb, {}),
            ("resend", family, body_a, ra, ta, {"predicted_reuse": p}))
    recs = {}
    for role, child, body, rendered, toks, extra in plan:
        fields = {**base, "role": role, "child": child, "loaded_before": _loaded(client),
                  "server": _server(_child_props(client, child)), **extra}
        recs[role] = st.send(client, body, rendered, toks, fields)
    return evaluate_trial(recs, st.requests_dir, hyp, family, child_b)


def _restart_trials(st, client, handle, controls, engine, system_text, tools, hyp, family, rep, n_ctx, run_id):
    last = None
    for part in ("restart", "save-restore"):
        nonce = new_nonce(controls.nonce_bytes)
        body = build_body(controls, system_text, tools, nonce, family)
        rendered, toks = _prepare(client, body, None)
        if len(toks) >= n_ctx:
            return None
        p = prediction(hyp, part, len(toks))
        base = {"repetition": rep, "part": part, "nonce": nonce, "child": family}
        server = _server(client.props())
        recs = {"anchor": st.send(client, body, rendered, toks, {**base, "role": "anchor", "server": server,
                                                                  "process": handle.info()})}
        actions = {}
        filename = f"{run_id}-r{rep}.bin"
        if part == "save-restore":
            actions["slot_save"] = client._call("/slots/0?action=save", json.dumps({"filename": filename}).encode("utf-8"))
        handle.stop()
        handle.start()
        props = client.props()
        _gate_server(engine, props)
        _gate_slots(hyp, props)
        if part == "save-restore":
            actions["slot_restore"] = client._call("/slots/0?action=restore", json.dumps({"filename": filename}).encode("utf-8"))
        recs["resend"] = st.send(client, body, rendered, toks, {**base, "role": "resend", "server": _server(props),
                                                                "process": handle.info(), "predicted_reuse": p, **actions})
        last = evaluate_trial(recs, st.requests_dir, hyp, family, family)
        if last["failures"] or last["unmeasurable"]:
            return last
    return last


def probe(m6: M6Config, controls: ControlsConfig, hid: str, family: str, handle: ServerHandle,
          fixture: Path = FIXTURE) -> dict:
    hyp = m6.hypothesis(hid)
    child_b = m6.child_b.family
    system_text, tools = _fixture(fixture)
    handle.start()
    out = {"hypothesis": hid, "family": family, "mode": hyp.mode, "requests": []}
    try:
        client = Client(handle.url, controls.request_timeout_seconds)
        if hyp.mode == "router":
            _load(client, family)
            if hyp.models_max > 1:
                _load(client, child_b)
            out["router_props"] = client.props()
            out["loaded"] = _loaded(client)
            nonce = new_nonce(controls.nonce_bytes)
            for role, child in (("anchor", family), ("other", child_b), ("resend", family)):
                body = build_body(controls, system_text, tools, nonce, child)
                rendered, toks = _prepare(client, body, child)
                before = _loaded(client)
                r = client.chat(body)
                out["requests"].append({"role": role, "child": child, "n": len(toks), "loaded_before": before,
                                        "props": _server(_child_props(client, child)), "response_model": r.get("model"),
                                        "observed": observed(r), "rendered_head": rendered[:80]})
            out["predicted_resend"] = prediction(hyp, None, out["requests"][0]["n"])
        else:
            for part in ("restart", "save-restore"):
                nonce = new_nonce(controls.nonce_bytes)
                body = build_body(controls, system_text, tools, nonce, family)
                rendered, toks = _prepare(client, body, None)
                first = observed(client.chat(body))
                actions = {}
                if part == "save-restore":
                    actions["save"] = client._call("/slots/0?action=save", json.dumps({"filename": "probe.bin"}).encode("utf-8"))
                handle.stop()
                handle.start()
                if part == "save-restore":
                    actions["restore"] = client._call("/slots/0?action=restore", json.dumps({"filename": "probe.bin"}).encode("utf-8"))
                second = observed(client.chat(body))
                out["requests"].append({"part": part, "n": len(toks), "anchor": first, "resend": second, **actions,
                                        "predicted_resend": prediction(hyp, part, len(toks)), "process": handle.info()})
    finally:
        handle.stop()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.m6")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "probe"):
        p = sub.add_parser(name)
        p.add_argument("--url", required=True, help="the address the server will answer on, e.g. http://127.0.0.1:8080")
        p.add_argument("--hypothesis", required=True, help="an id registered in config/m6.toml")
        p.add_argument("--family", required=True, help="child A: a family named in config/engines.toml")
        p.add_argument("--server-argv", required=True, help="JSON list: the server command line the driver starts and stops")
        p.add_argument("--server-log", required=True, help="file the server's output is appended to")
    sub.choices["run"].add_argument("--model-path", required=True, help="child A's model file")
    sub.choices["run"].add_argument("--child-b-path", default=None, help="child B's model file (router cells)")
    a = ap.parse_args(argv)
    try:
        m6 = load_m6_config(REPO_ROOT / "config" / "m6.toml", REPO_ROOT)
        controls = load_controls_config(REPO_ROOT / "config" / "controls.toml", REPO_ROOT)
        argv_list = json.loads(a.server_argv)
        if not isinstance(argv_list, list) or not all(isinstance(x, str) for x in argv_list):
            raise ValueError("--server-argv must be a JSON list of strings")
        handle = Subprocess(argv_list, a.url, Path(a.server_log))
        if a.cmd == "probe":
            print(json.dumps(probe(m6, controls, a.hypothesis, a.family, handle), indent=2, ensure_ascii=True))
            return 0
        engine = load_engines_config(REPO_ROOT / "config" / "engines.toml")["llamacpp"]
        report = run(m6, controls, engine, a.family, a.hypothesis, handle, Path(a.model_path),
                     Path(a.child_b_path) if a.child_b_path else None)
    except (Refusal, EngineError, ValueError, RuntimeError) as e:
        print(f"M6 REFUSED: {e}".encode("ascii", "backslashreplace").decode("ascii"), file=sys.stderr)
        return 2
    print(render(report).encode("ascii", "backslashreplace").decode("ascii"))
    return 0 if report["outcome"] == "ALL MATCH" else 1


if __name__ == "__main__":
    sys.exit(main())
