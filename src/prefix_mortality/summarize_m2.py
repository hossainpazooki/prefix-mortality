"""Serialization drift: recompute every trial from what is on disk, and refuse on any disagreement.

Nothing here talks to an engine. A trial is two requests under one nonce: the base request, then the
same request with its tools array written differently (serialize.py names the six ways). The rule and
the controls are those of pairs.py: the changed request's predicted reuse is the common token prefix
of the two renders (one slot) or that prefix above the similarity threshold (defaults), and an
identical render predicts n - 1, the identical-resend rule.

Two things are specific to this experiment. The summarizer checks that the two bodies differ only in
their `tools` text (`only_the_tools_changed`); any other difference is a failed control. And each
change carries a *reading* in the config, "identical" or "differs", of what the pinned source says
the render will do; the summarizer reports whether the render agreed with the reading. The reading
decides nothing: the prediction is from the render, and a wrong reading is a finding about the
parser, listed in the summary.
"""
import argparse
import json
import sys
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import M2Config, load_m2_config
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.pairs import evaluate_pair
from prefix_mortality.record import load_request, read

ROLES = ("base", "changed")
CONFIGS = ("controls", "engines", "m2")
THRESHOLD, MARGIN = 0.10, 0.002     # unused by the prefix rule; pairs.prediction needs values for the threshold rule


def _bodies_differ_only_in_tools(base_body: str, changed_body: str) -> bool:
    a, b = json.loads(base_body), json.loads(changed_body)
    return {k: v for k, v in a.items() if k != "tools"} == {k: v for k, v in b.items() if k != "tools"}


def evaluate_trial(base: dict, changed: dict, requests_dir: Path, cfg: M2Config, hid: str) -> dict:
    hyp = cfg.hypothesis(hid)
    out = evaluate_pair(base, changed, requests_dir, hyp.rule, THRESHOLD, MARGIN)
    out.update({"repetition": changed["repetition"], "change": changed["change"]})
    sb, sc = load_request(requests_dir, base["request_sha256"]), load_request(requests_dir, changed["request_sha256"])
    if out["match"] is not None and not _bodies_differ_only_in_tools(sb["body"], sc["body"]):
        out["failures"].append("only_the_tools_changed")
    reading = cfg.change(changed["change"]).reading
    out["reading"] = reading
    out["reading_agrees"] = (out["render_diff"] is None) == (reading == "identical")
    return out


def evaluate(records: list[dict], requests_dir: Path, cfg: M2Config) -> dict:
    if not records:
        raise ValueError("no record to evaluate")
    ids = {k: {r.get(k) for r in records} for k in ("run_id", "family", "hypothesis")}
    if any(len(v) != 1 for v in ids.values()):
        raise ValueError(f"records mix runs, families or hypotheses: {({k: sorted(map(str, v)) for k, v in ids.items()})}")
    hid = ids["hypothesis"].pop()
    hyp = cfg.hypothesis(hid)
    slots = {(r.get("server") or {}).get("total_slots") for r in records}
    if slots != {hyp.slots}:
        raise ValueError(f"{hid} requires a server reporting {hyp.slots} slot(s); the records say {sorted(map(str, slots))}. "
                         "This run is not that experiment")
    order = {c.id: i for i, c in enumerate(cfg.changes)}
    trials: dict[tuple[int, str], dict] = {}
    for r in records:
        if r.get("change") not in order or r.get("role") not in ROLES:
            raise ValueError(f"record {r.get('seq')}: unregistered change or role ({r.get('change')!r}, {r.get('role')!r})")
        slot = trials.setdefault((r["repetition"], r["change"]), {})
        if r["role"] in slot:
            raise ValueError(f"repetition {r['repetition']} {r['change']}: repeated {r['role']} record")
        slot[r["role"]] = r
    out, failures, unmeasurable, mismatches, disagreeing = [], [], [], [], []
    for rep, cid in sorted(trials, key=lambda k: (k[0], order[k[1]])):
        got, label = trials[(rep, cid)], f"repetition {rep} {cid}"
        if set(got) != set(ROLES):
            failures.append(f"{label}: no {' or '.join(sorted(set(ROLES) - set(got)))} record")
            continue
        t = evaluate_trial(got["base"], got["changed"], requests_dir, cfg, hid)
        out.append(t)
        unmeasurable += [f"{label} {x}" for x in t["unmeasurable"]]
        failures += [f"{label}: {x} is false" for x in t["failures"]]
        if not t["reading_agrees"]:
            disagreeing.append(label)
        if t["match"] is None or t["failures"]:
            continue
        if not t["match"]:
            mismatches.append(f"{label}: predicted {t['changed']['predicted_reuse']}, reused {t['changed']['cache_n']}")
    outcome = ("NOT MEASURABLE" if unmeasurable else "FAILED CONTROL" if failures
               else "MISMATCH" if mismatches else "ALL MATCH")
    return {"run_id": ids["run_id"].pop(), "family": ids["family"].pop(), "hypothesis": hid, "rule": hyp.rule,
            "slots": hyp.slots, "trials": out, "unmeasurable": unmeasurable, "failures": failures,
            "mismatches": mismatches, "readings_disagreeing": disagreeing, "outcome": outcome}


def render(report: dict) -> str:
    counted = [t for t in report["trials"] if t["match"] is not None and not t["failures"]]
    show = lambda v: "NOT MEASURABLE" if v is None else str(v)
    lines = [f"m2 {report['run_id']} ({report['family']}, {report['hypothesis']}, rule {report['rule']}, "
             f"{report['slots']} slot(s)): {report['outcome']}",
             f"trials counted: {len(counted)}; matching: {sum(t['match'] for t in counted)}; "
             f"readings disagreeing: {len(report['readings_disagreeing'])}", "",
             "| rep | change | prompt tokens | render differs at char | first differing token | reading | predicted | reused | result |",
             "|---|---|---|---|---|---|---|---|---|"]
    for t in report["trials"]:
        c = t["changed"]
        result = ("not evaluated" if t["match"] is None else "FAILED CONTROL: " + ", ".join(t["failures"]) if t["failures"]
                  else "match" if t["match"] else "MISMATCH")
        lines.append(f"| {t['repetition']} | {t['change']} | {c['n']} | {'identical' if t['render_diff'] is None else t['render_diff']} | "
                     f"{c['first_differing_token']} | {t['reading']}{'' if t['reading_agrees'] else ' (disagrees)'} | "
                     f"{c['predicted_reuse']} | {show(c['cache_n'])} | {result} |")
    for x in report["unmeasurable"] + report["failures"] + report["mismatches"]:
        lines.append(f"- {x}")
    return "\n".join(lines) + "\n"


def summarize(run_id: str, repo_root: Path = REPO_ROOT) -> tuple[dict, str]:
    cfg = load_m2_config(repo_root / "config" / "m2.toml", repo_root)
    records = read(cfg.corpus_dir / f"{run_id}.jsonl")
    current = {k: sha256_text_file(repo_root / "config" / f"{k}.toml") for k in CONFIGS}
    for r in records:
        if r.get("config_sha256") != current:
            raise ValueError(f"record {r.get('seq')} was written under a different config than the one on disk")
    rp = cfg.results_dir / run_id / "report.json"
    if not rp.exists():
        raise ValueError(f"{rp} does not exist; the driver wrote no report for this run")
    recorded = json.loads(rp.read_text(encoding="utf-8"))
    report = evaluate(records, repo_root / "corpus" / "requests", cfg)
    if report != recorded:
        diff = sorted(k for k in set(report) | set(recorded) if report.get(k) != recorded.get(k))
        raise ValueError(f"the records do not reproduce the driver's report; differing keys: {diff}")
    text = render(report)
    (cfg.results_dir / run_id / "summary.md").write_text(text, encoding="utf-8", newline="\n")
    return report, text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.summarize_m2")
    ap.add_argument("--run", required=True, help="run id, the name of the record file without .jsonl")
    a = ap.parse_args(argv)
    try:
        report, text = summarize(a.run)
    except (ValueError, KeyError) as e:
        print(f"SUMMARY REFUSED: {e}".encode("ascii", "backslashreplace").decode("ascii"))
        return 2
    print(text.encode("ascii", "backslashreplace").decode("ascii"))
    return 0 if report["outcome"] == "ALL MATCH" else 1


if __name__ == "__main__":
    sys.exit(main())
