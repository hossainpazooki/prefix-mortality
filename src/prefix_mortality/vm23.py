"""Templating (vm3) and serialization drift (vm2) on V, run against one vLLM server under one
hypothesis (one block size).

A trial is two requests under one fresh nonce: the base request, then the variant the arm names.
vm3's arms change only `chat_template_kwargs` (Qwen's thinking switch); vm2's arms rewrite the tool
schemas without changing their JSON value (function key order reversed; the same tools embedded as
indented JSON text). The variant is rendered, tokenized and stored before it is sent, and its
predicted counters are vm1's registered formula over the two stored token lists and the hypothesis's
block size — an identical render prices as an identical resend (d = n, so cached =
floor((n − 1)/B)·B), with no special case.

A prediction that is not met is a result, and the run goes on. The run stops when a trial fails a
control or a field is NOT MEASURABLE. `run` refuses unless the three configs are registered, the
block size is registered in config/vllm.toml, every pinned model file hashes to its digest, and the
server reports the pinned version and model. `probe` runs one trial per arm and records nothing.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import (ControlsConfig, VFamilyConfig, VllmConfig, VmArmConfig, load_controls_config,
                                     load_vllm_config, load_vm2_config, load_vm3_config)
from prefix_mortality.controls import FIXTURE, Refusal
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.nonce import new_nonce
from prefix_mortality.record import SCHEMA_VERSION, append, store_request, utc_now
from prefix_mortality.summarize_vm1 import evaluate_trial, prediction
from prefix_mortality.summarize_vm23 import evaluate, render
from prefix_mortality.vcontrols import _family_model, _gate_local, _gate_server, _maybe_vfamily, build_body
from prefix_mortality.vllm import Client, EngineError, observed


def variant_body(cfg: VmArmConfig, controls: ControlsConfig, served: str, arm: str, system_text: str,
                 tools: list, nonce: str) -> bytes:
    """The arm's variant of the base request, same nonce. Each construction is fixed here and named
    by the registering entry; an arm changes the request's bytes and nothing else about the trial."""
    if arm == "thinking-off":
        return build_body(controls, served, system_text, tools, nonce,
                          template_kwargs={"enable_thinking": False})
    if arm == "thinking-on":
        return build_body(controls, served, system_text, tools, nonce,
                          template_kwargs={"enable_thinking": True})
    if arm == "keyorder":
        rewritten = [{"function": {k: t["function"][k] for k in reversed(list(t["function"]))},
                      "type": t["type"]} for t in tools]
        return build_body(controls, served, system_text, rewritten, nonce)
    if arm == "properties":
        # reverse the key order of parameters.properties in every tool that has two or more: the same
        # JSON value, an order the template preserves (probe 2026-10-11, matching llama.cpp's S4)
        rewritten, changed = json.loads(json.dumps(tools)), 0
        for t in rewritten:
            props = t.get("function", {}).get("parameters", {}).get("properties")
            if isinstance(props, dict) and len(props) >= 2:
                t["function"]["parameters"]["properties"] = {k: props[k] for k in reversed(list(props))}
                changed += 1
        if not changed:
            raise Refusal("the properties arm needs a tool with at least two properties; the corpus has none")
        return build_body(controls, served, system_text, rewritten, nonce)
    raise Refusal(f"unknown arm {arm!r}")


def run(cfg: VmArmConfig, controls: ControlsConfig, vllm: VllmConfig, family: str, hid: str,
        client: Client, model_dir: Path, repo_root: Path = REPO_ROOT, fixture: Path = FIXTURE,
        vfam: VFamilyConfig | None = None) -> dict:
    hyp = cfg.hypothesis(hid)
    if not cfg.registered_by:
        raise Refusal(f"{cfg.config_path.name} is UNREGISTERED (registered_by is empty); a ledger entry registers it first")
    _gate_local(controls, vllm, family, hyp.block_size, Path(model_dir), vfam)
    model, served = _family_model(vllm, family, vfam)
    server = _gate_server(vllm, client, served)
    system_text = (fixture / "system.txt").read_bytes().decode("utf-8")
    tools = json.loads((fixture / "tools.json").read_text(encoding="utf-8"))
    requests_dir = repo_root / "corpus" / "requests"
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{family}-{hid}"
    log = cfg.corpus_dir / f"{run_id}.jsonl"
    if log.exists():
        raise Refusal(f"{log} already exists; a run never appends to another run's records")
    hashes = {"controls": sha256_text_file(controls.config_path), "vllm": sha256_text_file(vllm.config_path),
              cfg.experiment: sha256_text_file(cfg.config_path)}
    if vfam is not None and family == vfam.model.family:
        hashes[vfam.config_path.stem] = sha256_text_file(vfam.config_path)   # "vsm3", ...
    common = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "experiment": cfg.experiment,
              "hypothesis": hid, "family": family, "engine_repo": vllm.repo, "engine_commit": vllm.commit,
              "engine_version": vllm.version, "served_model_name": served,
              "dtype": vllm.dtype, "max_model_len": vllm.max_model_len,
              "kvcache_space_gib": vllm.kvcache_space_gib, "block_size": hyp.block_size,
              "model_hf_repo": model.hf_repo,
              "model_files": [{"name": f.name, "sha256": f.sha256} for f in model.files],
              "server": server,
              "config_sha256": hashes}
    records, seq, prev_base_ids, halted = [], 0, None, False
    for rep in range(1, cfg.repetitions + 1):
        for arm in cfg.arms:
            nonce = new_nonce(controls.nonce_bytes)
            base_body = build_body(controls, served, system_text, tools, nonce)
            var_body = variant_body(cfg, controls, served, arm, system_text, tools, nonce)
            base_ids: list[int] = []
            for role, body in (("base", base_body), ("edited", var_body)):
                prepared = client.prepare(body)
                ids = [t["id"] for t in prepared["tokens"]]
                sha = store_request(requests_dir, body, prepared["rendered"], prepared["tokens"])
                # computed from the two stored prompts alone, before the variant is sent
                extra = prediction(base_ids, ids, hyp.block_size) if role == "edited" else {}
                start = utc_now()
                response = client.chat(body)
                seq += 1
                rec = {**common, "seq": seq, "repetition": rep, "site": arm, "role": role, "nonce": nonce,
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


def probe(cfg: VmArmConfig, controls: ControlsConfig, vllm: VllmConfig, hid: str, arms: list[str],
          client: Client, fixture: Path = FIXTURE) -> dict:
    hyp = cfg.hypothesis(hid)
    unknown = [a for a in arms if a not in cfg.arms]
    if unknown:
        raise Refusal(f"unknown arm(s) {unknown}; known: {list(cfg.arms)}")
    server = {"version": client.version(), "model_ids": client.model_ids()}
    system_text = (fixture / "system.txt").read_bytes().decode("utf-8")
    tools = json.loads((fixture / "tools.json").read_text(encoding="utf-8"))
    trials = []
    for arm in arms:
        nonce = new_nonce(controls.nonce_bytes)
        base_body = build_body(controls, vllm.served_model_name, system_text, tools, nonce)
        var_body = variant_body(cfg, controls, vllm.served_model_name, arm, system_text, tools, nonce)
        pb, pv = client.prepare(base_body), client.prepare(var_body)
        base_ids, var_ids = [t["id"] for t in pb["tokens"]], [t["id"] for t in pv["tokens"]]
        p = prediction(base_ids, var_ids, hyp.block_size)
        first, second = client.chat(base_body), client.chat(var_body)
        ov = observed(second)
        trials.append({"arm": arm, "base_tokens": len(base_ids), "variant_tokens": len(var_ids),
                       "renders_identical": base_ids == var_ids, **p,
                       "base": {"observed": observed(first)}, "variant": {"observed": ov},
                       "match": (ov["usage_cached_tokens"] == p["predicted_cached"]
                                 and ov["usage_created_cache_tokens"] == p["predicted_created"])})
    return {"server": server, "hypothesis": hid, "block_size": hyp.block_size, "trials": trials}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.vm23")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "probe"):
        p = sub.add_parser(name)
        p.add_argument("--experiment", required=True, choices=("vm2", "vm3"))
        p.add_argument("--url", required=True, help="the server's address, e.g. http://127.0.0.1:8081")
        p.add_argument("--hypothesis", required=True)
    sub.choices["run"].add_argument("--family", required=True)
    sub.choices["run"].add_argument("--model-dir", required=True, help="folder holding the pinned model files")
    sub.choices["probe"].add_argument("--arms", required=True, help="comma-separated arm names")
    a = ap.parse_args(argv)
    try:
        loader = load_vm2_config if a.experiment == "vm2" else load_vm3_config
        cfg = loader(REPO_ROOT / "config" / f"{a.experiment}.toml", REPO_ROOT)
        controls = load_controls_config(REPO_ROOT / "config" / "controls.toml", REPO_ROOT)
        vllm = load_vllm_config(REPO_ROOT / "config" / "vllm.toml", REPO_ROOT)
        client = Client(a.url, controls.request_timeout_seconds)
        if a.cmd == "probe":
            print(json.dumps(probe(cfg, controls, vllm, a.hypothesis, a.arms.split(","), client),
                             indent=2, ensure_ascii=True))
            return 0
        vfam = _maybe_vfamily(vllm, a.family)
        report = run(cfg, controls, vllm, a.family, a.hypothesis, client, Path(a.model_dir), vfam=vfam)
    except (Refusal, EngineError, ValueError) as e:
        print(f"VM23 REFUSED: {e}".encode("ascii", "backslashreplace").decode("ascii"), file=sys.stderr)
        return 2
    print(render(report).encode("ascii", "backslashreplace").decode("ascii"))
    return 0 if report["outcome"] == "ALL MATCH" else 1


if __name__ == "__main__":
    sys.exit(main())
