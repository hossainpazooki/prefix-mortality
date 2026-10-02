"""Templating: recompute every trial from what is on disk, and refuse on any disagreement.

Nothing here talks to an engine. A trial is two requests under one nonce whose messages and tools are
the same bytes and whose `chat_template_kwargs` differ in exactly one registered key: the base request
carries the registered base arguments, the changed request the same with one value replaced. The
rule and the controls are those of pairs.py; the only check specific to this experiment is that the
two bodies differ in nothing but `chat_template_kwargs` (`only_kwargs_changed`).
"""
import argparse
import json
import sys
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import M3Config, load_m3_config
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.pairs import evaluate_pair
from prefix_mortality.record import load_request, read

ROLES = ("base", "changed")
CONFIGS = ("controls", "engines", "m3")


def _only_kwargs_changed(base_body: str, changed_body: str, change_key: str) -> bool:
    a, b = json.loads(base_body), json.loads(changed_body)
    same_rest = ({k: v for k, v in a.items() if k != "chat_template_kwargs"}
                 == {k: v for k, v in b.items() if k != "chat_template_kwargs"})
    ka, kb = a.get("chat_template_kwargs") or {}, b.get("chat_template_kwargs") or {}
    return (same_rest and set(ka) == set(kb) and all(ka[k] == kb[k] for k in ka if k != change_key)
            and ka.get(change_key) != kb.get(change_key))


def evaluate_trial(base: dict, changed: dict, requests_dir: Path, cfg: M3Config, hid: str) -> dict:
    hyp = cfg.hypothesis(hid)
    out = evaluate_pair(base, changed, requests_dir, hyp.rule, cfg.similarity_threshold, cfg.threshold_margin)
    out.update({"repetition": changed["repetition"], "change": changed["change"]})
    sb, sc = load_request(requests_dir, base["request_sha256"]), load_request(requests_dir, changed["request_sha256"])
    if out["match"] is not None and not _only_kwargs_changed(sb["body"], sc["body"], cfg.change(changed["change"]).key):
        out["failures"].append("only_kwargs_changed")
    return out


def evaluate(records: list[dict], requests_dir: Path, cfg: M3Config) -> dict:
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
    out, failures, unmeasurable, mismatches, excluded = [], [], [], [], []
    for rep, cid in sorted(trials, key=lambda k: (k[0], order[k[1]])):
        got, label = trials[(rep, cid)], f"repetition {rep} {cid}"
        if set(got) != set(ROLES):
            failures.append(f"{label}: no {' or '.join(sorted(set(ROLES) - set(got)))} record")
            continue
        t = evaluate_trial(got["base"], got["changed"], requests_dir, cfg, hid)
        out.append(t)
        unmeasurable += [f"{label} {x}" for x in t["unmeasurable"]]
        failures += [f"{label}: {x} is false" for x in t["failures"]]
        if t["match"] is None or t["failures"]:
            continue
        if t["changed"]["near_threshold"]:
            excluded.append(label)
        elif not t["match"]:
            mismatches.append(f"{label}: predicted {t['changed']['predicted_reuse']}, reused {t['changed']['cache_n']}")
    outcome = ("NOT MEASURABLE" if unmeasurable else "FAILED CONTROL" if failures
               else "MISMATCH" if mismatches else "ALL MATCH")
    return {"run_id": ids["run_id"].pop(), "family": ids["family"].pop(), "hypothesis": hid, "rule": hyp.rule,
            "slots": hyp.slots, "base_kwargs": cfg.base_kwargs, "similarity_threshold": cfg.similarity_threshold,
            "threshold_margin": cfg.threshold_margin, "trials": out, "unmeasurable": unmeasurable,
            "failures": failures, "mismatches": mismatches, "excluded": excluded, "outcome": outcome}


def render(report: dict) -> str:
    counted = [t for t in report["trials"] if t["match"] is not None and not t["failures"] and not t["changed"]["near_threshold"]]
    show = lambda v: "NOT MEASURABLE" if v is None else str(v)
    lines = [f"m3 {report['run_id']} ({report['family']}, {report['hypothesis']}, rule {report['rule']}, "
             f"{report['slots']} slot(s)): {report['outcome']}",
             f"trials counted: {len(counted)}; matching: {sum(t['match'] for t in counted)}; "
             f"not counted, near the threshold: {len(report['excluded'])}", "",
             "| rep | change | prompt tokens | render differs at char | first differing token | share of the prompt | predicted | reused | result |",
             "|---|---|---|---|---|---|---|---|---|"]
    for t in report["trials"]:
        c = t["changed"]
        result = ("not evaluated" if t["match"] is None else "FAILED CONTROL: " + ", ".join(t["failures"]) if t["failures"]
                  else "not counted" if c["near_threshold"] else "match" if t["match"] else "MISMATCH")
        lines.append(f"| {t['repetition']} | {t['change']} | {c['n']} | {'identical' if t['render_diff'] is None else t['render_diff']} | "
                     f"{c['first_differing_token']} | {c['first_differing_token'] / c['n']:.4f} | {c['predicted_reuse']} | "
                     f"{show(c['cache_n'])} | {result} |")
    for x in report["unmeasurable"] + report["failures"] + report["mismatches"]:
        lines.append(f"- {x}")
    return "\n".join(lines) + "\n"


def summarize(run_id: str, repo_root: Path = REPO_ROOT) -> tuple[dict, str]:
    cfg = load_m3_config(repo_root / "config" / "m3.toml", repo_root)
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
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.summarize_m3")
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
