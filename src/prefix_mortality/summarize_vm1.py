"""Edit position on V: recompute every trial from what is on disk, and refuse on any disagreement.

Nothing here talks to an engine. A trial is two requests under one nonce: the base request, then the
same request with one word replaced at a registered site. From the stored token ids of both:

  d  the leading tokens the two prompts have in common: the position of the edit, in the engine's
     own tokens, of the prompt as the engine rendered it
  n  the token count of the edited prompt

and the edited request's counters follow from the hypothesis's block size B (rules of entry 0022,
validated by 0024: a hit is a stored block chain, block-aligned, capped at n - 1; created is
finalized before any generated token is cached):

  cached  = floor(min(d, n - 1) / B) * B
  created = floor(n / B) * B - cached

The base request is held to the controls' write rule: cached 0 and created = floor(n/B)*B. Its zero
is exact only while it shares fewer than B leading tokens with the previous trial's base (fresh
nonces; checked per trial from the stored ids; the first trial of a run meets a fresh server's empty
cache). A prediction that is not met is a result (MISMATCH) and the run goes on; a failed base
control or a missing field ends the run, because nothing after it can be read. A field the server
did not report is never read as zero.

A run's outcome is ALL MATCH, MISMATCH, FAILED CONTROL or NOT MEASURABLE. A verdict on a hypothesis
is stated by a ledger entry from the run's outcome.
"""
import argparse
import json
import sys
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import Vm1Config, load_controls_config, load_vllm_config, load_vm1_config
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.record import load_request, read
from prefix_mortality.summarize_vcontrols import FIELDS, _lcp

ROLES = ("base", "edited")
CONFIGS = ("controls", "vllm", "vm1")


def prediction(base_ids: list[int], edited_ids: list[int], block: int) -> dict:
    """What the driver stores before it sends the edited request, and what is recomputed here."""
    d, n = _lcp(base_ids, edited_ids), len(edited_ids)
    cached = (min(d, n - 1) // block) * block
    return {"first_differing_token": d, "predicted_cached": cached,
            "predicted_created": (n // block) * block - cached}


def _derive(record: dict, requests_dir: Path) -> dict:
    stored = load_request(requests_dir, record["request_sha256"])
    o = record["observed"]
    return {"request_sha256": record["request_sha256"], "n": len(stored["tokens"]),
            "ids": [t["id"] for t in stored["tokens"]], **{f: o.get(f) for f in FIELDS}}


def evaluate_trial(base: dict, edited: dict, prev_base_ids: list[int] | None, requests_dir: Path,
                   block: int) -> dict:
    """One trial from its two records. `failures` are failed controls; `match` is the result."""
    db, de = _derive(base, requests_dir), _derive(edited, requests_dir)
    out = {"repetition": edited["repetition"], "site": edited["site"],
           "failures": [], "unmeasurable": [], "match": None}
    for role, d in (("base", db), ("edited", de)):
        missing = [f for f in FIELDS if d[f] is None]
        if missing:
            out["unmeasurable"].append(f"{role}: the server reported no {', '.join(missing)}")
    if out["unmeasurable"]:
        return out
    for role, d in (("base", db), ("edited", de)):
        if d["usage_prompt_tokens"] != d["n"]:
            out["failures"].append(f"{role}: size_agrees is false")
    if db["usage_cached_tokens"] != 0:
        out["failures"].append("base: cached is not 0; the trial was not isolated")
    if db["usage_created_cache_tokens"] != (db["n"] // block) * block:
        out["failures"].append("base: created is not the write rule's value")
    if prev_base_ids is not None and _lcp(db["ids"], prev_base_ids) >= block:
        out["failures"].append("base: shares a full block with the previous trial's base; its zero is not exact")
    p = prediction(db["ids"], de["ids"], block)
    out.update(p, n=de["n"], share_of_the_prompt=round(p["first_differing_token"] / de["n"], 4),
               base_n=db["n"], observed_cached=de["usage_cached_tokens"],
               observed_created=de["usage_created_cache_tokens"])
    stored = {k: edited.get(k) for k in p}
    if stored != p:
        out["failures"].append(f"edited: the stored prediction {stored} is not the recomputation {p}")
    if not out["failures"]:
        out["match"] = (de["usage_cached_tokens"] == p["predicted_cached"]
                        and de["usage_created_cache_tokens"] == p["predicted_created"])
    return out


def evaluate(records: list[dict], requests_dir: Path, cfg: Vm1Config, block_sizes: tuple[int, ...]) -> dict:
    if not records:
        raise ValueError("no record to evaluate")
    for key in ("run_id", "family", "hypothesis", "block_size"):
        if len({r.get(key) for r in records}) != 1:
            raise ValueError(f"records mix values of {key}: {sorted({str(r.get(key)) for r in records})}")
    hid = records[0]["hypothesis"]
    block = cfg.hypothesis(hid).block_size
    if records[0]["block_size"] != block:
        raise ValueError(f"records say block size {records[0]['block_size']}; {hid} registers {block}")
    if block not in block_sizes:
        raise ValueError(f"block size {block} is not registered; registered: {list(block_sizes)}")
    if len(records) % 2:
        raise ValueError("an odd number of records; a trial is a base and an edited request")
    trials, prev_base_ids = [], None
    for base, edited in zip(records[::2], records[1::2]):
        if (base["role"], edited["role"]) != ROLES or base["site"] != edited["site"] \
                or base["nonce"] != edited["nonce"]:
            raise ValueError(f"records out of order at seq {base.get('seq')}: a trial is base then "
                             "edited, one site, one nonce")
        trials.append(evaluate_trial(base, edited, prev_base_ids, requests_dir, block))
        prev_base_ids = _derive(base, requests_dir)["ids"]
    failures = [f"repetition {t['repetition']} {t['site']}: {m}" for t in trials for m in t["failures"]]
    unmeasurable = [f"repetition {t['repetition']} {t['site']}: {m}" for t in trials for m in t["unmeasurable"]]
    mismatches = [t for t in trials if t["match"] is False]
    outcome = ("NOT MEASURABLE" if unmeasurable else "FAILED CONTROL" if failures
               else "MISMATCH" if mismatches else "ALL MATCH")
    return {"run_id": records[0]["run_id"], "family": records[0]["family"], "hypothesis": hid,
            "block_size": block, "trials": trials, "matching_trials": sum(1 for t in trials if t["match"]),
            "trial_count": len(trials), "failures": failures, "unmeasurable": unmeasurable,
            "outcome": outcome}


def render(report: dict) -> str:
    head = (f"vm1 {report['run_id']} ({report['hypothesis']}, block {report['block_size']}): "
            f"{report['outcome']}, {report['matching_trials']} of {report['trial_count']} trials match\n")
    lines = ["| rep | site | d | share | n | predicted cached/created | observed | match |",
             "|---|---|---|---|---|---|---|---|"]
    for t in report["trials"]:
        if t["unmeasurable"] or t["failures"]:
            lines.append(f"| {t['repetition']} | {t['site']} | - | - | - | - | - | "
                         f"{'; '.join(t['unmeasurable'] + t['failures'])} |")
            continue
        lines.append(f"| {t['repetition']} | {t['site']} | {t['first_differing_token']} | "
                     f"{t['share_of_the_prompt']} | {t['n']} | {t['predicted_cached']}/{t['predicted_created']} | "
                     f"{t['observed_cached']}/{t['observed_created']} | {t['match']} |")
    tail = "".join(f"\n{k}: {m}" for k in ("failures", "unmeasurable") for m in report[k])
    return head + "\n" + "\n".join(lines) + (tail + "\n" if tail else "")


def summarize(run_id: str, repo_root: Path = REPO_ROOT) -> dict:
    controls = load_controls_config(repo_root / "config" / "controls.toml", repo_root)
    vllm = load_vllm_config(repo_root / "config" / "vllm.toml", repo_root)
    cfg = load_vm1_config(repo_root / "config" / "vm1.toml", repo_root)
    records = read(cfg.corpus_dir / f"{run_id}.jsonl")
    current = {"controls": sha256_text_file(controls.config_path), "vllm": sha256_text_file(vllm.config_path),
               "vm1": sha256_text_file(cfg.config_path)}
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
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.summarize_vm1")
    ap.add_argument("--run", required=True)
    a = ap.parse_args(argv)
    try:
        report = summarize(a.run)
    except (OSError, ValueError) as e:
        print(f"SUMMARIZE REFUSED: {e}".encode("ascii", "backslashreplace").decode("ascii"), file=sys.stderr)
        return 2
    print(render(report).encode("ascii", "backslashreplace").decode("ascii"))
    return 0 if report["outcome"] == "ALL MATCH" else 1


if __name__ == "__main__":
    sys.exit(main())
