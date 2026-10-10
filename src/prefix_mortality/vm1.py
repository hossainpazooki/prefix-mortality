"""Edit position on V, run against one vLLM server under one hypothesis (one block size).

A trial is two requests under one fresh nonce: the base request, then the same request with one word
replaced at a registered site. The edited request is rendered, tokenized and stored before it is
sent, and its predicted counters are a function of the two stored token lists and the hypothesis's
block size, nothing else. The record carries the prediction; `summarize_vm1` states the rules and
recomputes every trial, prediction included, from disk. This module sends and records.

A prediction that is not met is a result, and the run goes on. The run stops only when a trial fails
a control or a field is NOT MEASURABLE, because nothing after that can be read.

`run` refuses unless the three configs are registered, the hypothesis's block size is registered in
config/vllm.toml, every pinned model file hashes to its digest, and the server reports the pinned
version and serves the registered model name. The server is started fresh per run with the
hypothesis's `--block-size`; it does not report the block size, and the records read it back only
through the block arithmetic. `probe` runs one trial per site it is given, prints what came back and
records nothing.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import (ControlsConfig, VllmConfig, Vm1Config, load_controls_config,
                                     load_vllm_config, load_vm1_config)
from prefix_mortality.controls import FIXTURE, Refusal
from prefix_mortality.edits import apply, site_names
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.nonce import new_nonce
from prefix_mortality.record import SCHEMA_VERSION, append, store_request, utc_now
from prefix_mortality.summarize_vm1 import evaluate, evaluate_trial, prediction, render
from prefix_mortality.vcontrols import _gate_local, _gate_server, build_body
from prefix_mortality.vllm import Client, EngineError, observed


def _bodies(controls: ControlsConfig, cfg: Vm1Config, served: str, site: str, system_text: str,
            tools: list, nonce: str) -> tuple[bytes, bytes]:
    base = build_body(controls, served, system_text, tools, nonce)
    s, t, u = apply(site, system_text, tools, controls.user_message, cfg.replacement)
    return base, build_body(controls, served, s, t, nonce, user_message=u)


def run(cfg: Vm1Config, controls: ControlsConfig, vllm: VllmConfig, family: str, hid: str, client: Client,
        model_dir: Path, repo_root: Path = REPO_ROOT, fixture: Path = FIXTURE) -> dict:
    hyp = cfg.hypothesis(hid)
    if not cfg.registered_by:
        raise Refusal(f"{cfg.config_path.name} is UNREGISTERED (registered_by is empty); a ledger entry registers it first")
    _gate_local(controls, vllm, family, hyp.block_size, Path(model_dir))
    server = _gate_server(vllm, client)
    system_text = (fixture / "system.txt").read_bytes().decode("utf-8")
    tools = json.loads((fixture / "tools.json").read_text(encoding="utf-8"))
    requests_dir = repo_root / "corpus" / "requests"
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{family}-{hid}"
    log = cfg.corpus_dir / f"{run_id}.jsonl"
    if log.exists():
        raise Refusal(f"{log} already exists; a run never appends to another run's records")
    model = vllm.model(family)
    common = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "experiment": "vm1", "hypothesis": hid,
              "family": family, "engine_repo": vllm.repo, "engine_commit": vllm.commit,
              "engine_version": vllm.version, "served_model_name": vllm.served_model_name,
              "dtype": vllm.dtype, "max_model_len": vllm.max_model_len,
              "kvcache_space_gib": vllm.kvcache_space_gib, "block_size": hyp.block_size,
              "model_hf_repo": model.hf_repo,
              "model_files": [{"name": f.name, "sha256": f.sha256} for f in model.files],
              "server": server,
              "config_sha256": {"controls": sha256_text_file(controls.config_path),
                                "vllm": sha256_text_file(vllm.config_path),
                                "vm1": sha256_text_file(cfg.config_path)}}
    records, seq, prev_base_ids, halted = [], 0, None, False
    for rep in range(1, cfg.repetitions + 1):
        for site in site_names(cfg):
            nonce = new_nonce(controls.nonce_bytes)
            base_body, edited_body = _bodies(controls, cfg, vllm.served_model_name, site, system_text,
                                             tools, nonce)
            base_ids: list[int] = []
            for role, body in (("base", base_body), ("edited", edited_body)):
                prepared = client.prepare(body)
                ids = [t["id"] for t in prepared["tokens"]]
                sha = store_request(requests_dir, body, prepared["rendered"], prepared["tokens"])
                # computed from the two stored prompts alone, before the edited request is sent
                extra = prediction(base_ids, ids, hyp.block_size) if role == "edited" else {}
                start = utc_now()
                response = client.chat(body)
                seq += 1
                rec = {**common, "seq": seq, "repetition": rep, "site": site, "role": role, "nonce": nonce,
                       "request_sha256": sha, "ts_start": start, "ts_end": utc_now(),
                       "local_date": datetime.now().strftime("%Y-%m-%d"), "observed": observed(response),
                       "usage_raw": response.get("usage"), **extra}
                append(log, rec)
                records.append(rec)
                base_ids = ids if role == "base" else base_ids
            trial = evaluate_trial(records[-2], records[-1], prev_base_ids, requests_dir, hyp.block_size)
            prev_base_ids = base_ids
            if trial["failures"] or trial["unmeasurable"]:
                halted = True
                break
        if halted:
            break
    report = evaluate(records, requests_dir, cfg, vllm.block_sizes)
    out = cfg.results_dir / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8",
                                     newline="\n")
    return report


def probe(cfg: Vm1Config, controls: ControlsConfig, vllm: VllmConfig, hid: str, sites: list[str],
          client: Client, fixture: Path = FIXTURE) -> dict:
    hyp = cfg.hypothesis(hid)
    unknown = [s for s in sites if s not in site_names(cfg)]
    if unknown:
        raise Refusal(f"unknown site(s) {unknown}; known: {site_names(cfg)}")
    server = {"version": client.version(), "model_ids": client.model_ids()}
    system_text = (fixture / "system.txt").read_bytes().decode("utf-8")
    tools = json.loads((fixture / "tools.json").read_text(encoding="utf-8"))
    trials = []
    for site in sites:
        nonce = new_nonce(controls.nonce_bytes)
        base_body, edited_body = _bodies(controls, cfg, vllm.served_model_name, site, system_text,
                                         tools, nonce)
        pb, pe = client.prepare(base_body), client.prepare(edited_body)
        base_ids, edited_ids = [t["id"] for t in pb["tokens"]], [t["id"] for t in pe["tokens"]]
        p = prediction(base_ids, edited_ids, hyp.block_size)
        first, second = client.chat(base_body), client.chat(edited_body)
        oe = observed(second)
        trials.append({"site": site, "prompt_tokens": len(edited_ids), **p,
                       "share_of_the_prompt": round(p["first_differing_token"] / len(edited_ids), 4),
                       "base": {"observed": observed(first)}, "edited": {"observed": oe},
                       "match": (oe["usage_cached_tokens"] == p["predicted_cached"]
                                 and oe["usage_created_cache_tokens"] == p["predicted_created"])})
    return {"server": server, "hypothesis": hid, "block_size": hyp.block_size, "trials": trials}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.vm1")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "probe"):
        p = sub.add_parser(name)
        p.add_argument("--url", required=True, help="the server's address, e.g. http://127.0.0.1:8081")
        p.add_argument("--hypothesis", required=True, help="an id registered in config/vm1.toml")
    sub.choices["run"].add_argument("--family", required=True)
    sub.choices["run"].add_argument("--model-dir", required=True, help="folder holding the pinned model files")
    sub.choices["probe"].add_argument("--sites", required=True, help="comma-separated site names")
    a = ap.parse_args(argv)
    try:
        cfg = load_vm1_config(REPO_ROOT / "config" / "vm1.toml", REPO_ROOT)
        controls = load_controls_config(REPO_ROOT / "config" / "controls.toml", REPO_ROOT)
        vllm = load_vllm_config(REPO_ROOT / "config" / "vllm.toml", REPO_ROOT)
        client = Client(a.url, controls.request_timeout_seconds)
        if a.cmd == "probe":
            print(json.dumps(probe(cfg, controls, vllm, a.hypothesis, a.sites.split(","), client),
                             indent=2, ensure_ascii=True))
            return 0
        report = run(cfg, controls, vllm, a.family, a.hypothesis, client, Path(a.model_dir))
    except (Refusal, EngineError, ValueError) as e:
        print(f"VM1 REFUSED: {e}".encode("ascii", "backslashreplace").decode("ascii"), file=sys.stderr)
        return 2
    print(render(report).encode("ascii", "backslashreplace").decode("ascii"))
    return 0 if report["outcome"] == "ALL MATCH" else 1


if __name__ == "__main__":
    sys.exit(main())
