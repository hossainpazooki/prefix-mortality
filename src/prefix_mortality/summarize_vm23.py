"""Templating and serialization drift on V: recompute every trial from disk, refuse disagreement.

The trial shape, rules and outcome vocabulary are vm1's (summarize_vm1), applied to arm variants in
place of word edits: d is the leading tokens the base and the variant prompt share, n the variant's
token count, and the predicted counters are cached = floor(min(d, n − 1)/B)·B with created
completing floor(n/B)·B. An identical render has d = n and prices as an identical resend. This
module only resolves which experiment a run belongs to, pins its config hashes, and renders with the
experiment's own heading; the evaluation is summarize_vm1's, unchanged.
"""
import argparse
import json
import sys
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import VmArmConfig, load_controls_config, load_vllm_config, load_vm2_config, load_vm3_config
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.record import read
from prefix_mortality.summarize_vm1 import evaluate as _evaluate
from prefix_mortality.summarize_vm1 import render as _render

LOADERS = {"vm2": load_vm2_config, "vm3": load_vm3_config}


def evaluate(records: list[dict], requests_dir: Path, cfg: VmArmConfig, block_sizes: tuple[int, ...]) -> dict:
    arms = {r.get("site") for r in records}
    unknown = arms - set(cfg.arms)
    if unknown:
        raise ValueError(f"records carry unregistered arm(s) {sorted(map(str, unknown))}; "
                         f"registered: {list(cfg.arms)}")
    report = _evaluate(records, requests_dir, cfg, block_sizes)
    report["experiment"] = cfg.experiment
    return report


def render(report: dict) -> str:
    return report["experiment"] + _render(report).removeprefix("vm1")


def summarize(run_id: str, experiment: str, repo_root: Path = REPO_ROOT) -> dict:
    if experiment not in LOADERS:
        raise ValueError(f"unknown experiment {experiment!r}; known: {sorted(LOADERS)}")
    controls = load_controls_config(repo_root / "config" / "controls.toml", repo_root)
    vllm = load_vllm_config(repo_root / "config" / "vllm.toml", repo_root)
    cfg = LOADERS[experiment](repo_root / "config" / f"{experiment}.toml", repo_root)
    records = read(cfg.corpus_dir / f"{run_id}.jsonl")
    current = {"controls": sha256_text_file(controls.config_path), "vllm": sha256_text_file(vllm.config_path),
               experiment: sha256_text_file(cfg.config_path)}
    for r in records:
        if r.get("config_sha256") != current:
            raise ValueError(f"record {r.get('seq')} was written under a different config than the one on disk")
    rp = cfg.results_dir / run_id / "report.json"
    if not rp.exists():
        raise ValueError(f"{rp} does not exist; the driver wrote no report for this run")
    recorded = json.loads(rp.read_text(encoding="utf-8"))
    report = evaluate(records, repo_root / "corpus" / "requests", cfg, vllm.block_sizes)
    if report != recorded:
        keys = sorted(k for k in set(report) | set(recorded) if report.get(k) != recorded.get(k))
        raise ValueError(f"recomputation does not reproduce the driver's report; differing keys: {keys}")
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.summarize_vm23")
    ap.add_argument("--experiment", required=True, choices=sorted(LOADERS))
    ap.add_argument("--run", required=True)
    a = ap.parse_args(argv)
    try:
        report = summarize(a.run, a.experiment)
    except (OSError, ValueError) as e:
        print(f"SUMMARIZE REFUSED: {e}".encode("ascii", "backslashreplace").decode("ascii"), file=sys.stderr)
        return 2
    print(render(report).encode("ascii", "backslashreplace").decode("ascii"))
    return 0 if report["outcome"] == "ALL MATCH" else 1


if __name__ == "__main__":
    sys.exit(main())
