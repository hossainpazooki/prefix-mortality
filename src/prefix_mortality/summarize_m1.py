"""Edit position: recompute every trial from what is on disk, and refuse on any disagreement.

Nothing here talks to an engine. A trial is two requests under one nonce: the base request, then the
same request with one word replaced. From the stored tokens of both:

  d  the leading tokens the two prompts have in common: the position of the edit, in the engine's
     own tokens, of the prompt as the engine rendered it
  n  the token count of the edited prompt

and the predicted reuse of the edited request follows from the hypothesis's rule:

  prefix     d
  threshold  d when d / n is above the registered similarity threshold, else 0

The base request is held to the controls' rule for a write: it reuses at most h, the tokens that
start before the end of the nonce. If it does not, the trial was not isolated and the run has failed
a control; that is not a result about the hypothesis. A trial whose d / n lies within the registered
margin of the threshold is reported and not counted. A field the server did not report makes the run
NOT MEASURABLE. It is never read as zero.

A run's outcome is ALL MATCH, MISMATCH, FAILED CONTROL or NOT MEASURABLE. A verdict on a hypothesis
is stated by a ledger entry, from the outcomes of both models.
"""
import argparse
import json
import sys
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import M1Config, load_m1_config
from prefix_mortality.edits import site_names
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.record import load_request, read
from prefix_mortality.summarize import FIELDS, header_tokens

ROLES = ("base", "edited")
CONFIGS = ("controls", "engines", "m1")


def common_prefix(a: list[int], b: list[int]) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def predict(rule: str, d: int, n: int, threshold: float) -> int:
    if rule == "prefix":
        return d
    if rule == "threshold":
        return d if d / n > threshold else 0
    raise ValueError(f"unknown rule {rule!r}")


def near_threshold(rule: str, d: int, n: int, threshold: float, margin: float) -> bool:
    return rule == "threshold" and abs(d / n - threshold) < margin


def prediction(cfg: M1Config, hid: str, base_ids: list[int], edited_ids: list[int]) -> dict:
    """What the driver stores before it sends the edited request, and what is recomputed here."""
    rule = cfg.hypothesis(hid).rule
    d, n = common_prefix(base_ids, edited_ids), len(edited_ids)
    return {"first_differing_token": d, "predicted_reuse": predict(rule, d, n, cfg.similarity_threshold),
            "near_threshold": near_threshold(rule, d, n, cfg.similarity_threshold, cfg.threshold_margin)}


def _ids(stored: dict) -> list[int]:
    return [t["id"] for t in stored["tokens"]]


def evaluate_trial(base: dict, edited: dict, requests_dir: Path, cfg: M1Config, hid: str) -> dict:
    """One trial from its two records. `failures` are failed controls; `match` is the result."""
    sb, se = load_request(requests_dir, base["request_sha256"]), load_request(requests_dir, edited["request_sha256"])
    out = {"repetition": edited["repetition"], "site": edited["site"], "failures": [], "unmeasurable": []}
    rows = {}
    for role, rec, stored in (("base", base, sb), ("edited", edited, se)):
        o = rec["observed"]
        rows[role] = {"request_sha256": rec["request_sha256"], "n": len(stored["tokens"]),
                      "h": header_tokens(stored["tokens"], rec["nonce"]), **{f: o.get(f) for f in FIELDS}}
        missing = [f for f in FIELDS if rows[role][f] is None]
        if missing:
            out["unmeasurable"].append(f"{role}: the server reported no {', '.join(missing)}")
    p = prediction(cfg, hid, _ids(sb), _ids(se))
    rows["edited"].update(p)
    out.update(rows)
    out["match"] = None
    if out["unmeasurable"]:
        return out
    b, e = rows["base"], rows["edited"]
    checks = {"same_nonce": base["nonce"] == edited["nonce"],
              "edit_changed_the_prompt": p["first_differing_token"] < e["n"],
              "prediction_as_recorded": {k: edited.get(k) for k in p} == p,
              "base_reuses_at_most_header": b["cache_n"] <= b["h"],
              "base_counts_add_up": b["cache_n"] + b["prompt_n"] == b["n"],
              "base_fields_agree": b["usage_cached_tokens"] == b["cache_n"],
              "edited_counts_add_up": e["cache_n"] + e["prompt_n"] == e["n"],
              "edited_fields_agree": e["usage_cached_tokens"] == e["cache_n"]}
    out["failures"] = [k for k, ok in checks.items() if not ok]
    out["match"] = e["cache_n"] == e["predicted_reuse"]
    return out


def evaluate(records: list[dict], requests_dir: Path, cfg: M1Config) -> dict:
    if not records:
        raise ValueError("no record to evaluate")
    ids = {k: {r.get(k) for r in records} for k in ("run_id", "family", "hypothesis")}
    if any(len(v) != 1 for v in ids.values()):
        mixed = {k: sorted(map(str, v)) for k, v in ids.items()}
        raise ValueError(f"records mix runs, families or hypotheses: {mixed}")
    hid = ids["hypothesis"].pop()
    hyp = cfg.hypothesis(hid)
    slots = {(r.get("server") or {}).get("total_slots") for r in records}
    if slots != {hyp.slots}:
        raise ValueError(f"{hid} requires a server reporting {hyp.slots} slot(s); the records say {sorted(map(str, slots))}. "
                         "This run is not that experiment")
    order = {s: i for i, s in enumerate(site_names(cfg))}
    trials: dict[tuple[int, str], dict] = {}
    for r in records:
        if r.get("site") not in order or r.get("role") not in ROLES:
            raise ValueError(f"record {r.get('seq')}: unregistered site or role ({r.get('site')!r}, {r.get('role')!r})")
        slot = trials.setdefault((r["repetition"], r["site"]), {})
        if r["role"] in slot:
            raise ValueError(f"repetition {r['repetition']} site {r['site']}: repeated {r['role']} record")
        slot[r["role"]] = r

    out, failures, unmeasurable, mismatches, excluded = [], [], [], [], []
    for rep, site in sorted(trials, key=lambda k: (k[0], order[k[1]])):
        got, label = trials[(rep, site)], f"repetition {rep} {site}"
        if set(got) != set(ROLES):
            failures.append(f"{label}: no {' or '.join(sorted(set(ROLES) - set(got)))} record")
            continue
        t = evaluate_trial(got["base"], got["edited"], requests_dir, cfg, hid)
        out.append(t)
        unmeasurable += [f"{label} {x}" for x in t["unmeasurable"]]
        failures += [f"{label}: {x} is false" for x in t["failures"]]
        if t["match"] is None or t["failures"]:
            continue
        if t["edited"]["near_threshold"]:
            excluded.append(label)
        elif not t["match"]:
            mismatches.append(f"{label}: predicted {t['edited']['predicted_reuse']}, reused {t['edited']['cache_n']}")

    outcome = ("NOT MEASURABLE" if unmeasurable else "FAILED CONTROL" if failures
               else "MISMATCH" if mismatches else "ALL MATCH")
    return {"run_id": ids["run_id"].pop(), "family": ids["family"].pop(), "hypothesis": hid, "rule": hyp.rule,
            "slots": hyp.slots, "similarity_threshold": cfg.similarity_threshold,
            "threshold_margin": cfg.threshold_margin, "trials": out, "unmeasurable": unmeasurable,
            "failures": failures, "mismatches": mismatches, "excluded": excluded, "outcome": outcome}


def render(report: dict) -> str:
    counted = [t for t in report["trials"] if t["match"] is not None and not t["failures"]
               and not t["edited"]["near_threshold"]]
    lines = [f"m1 {report['run_id']} ({report['family']}, {report['hypothesis']}, rule {report['rule']}, "
             f"{report['slots']} slot(s)): {report['outcome']}",
             f"trials counted: {len(counted)}; matching: {sum(t['match'] for t in counted)}; "
             f"not counted, near the threshold: {len(report['excluded'])}", "",
             "| rep | site | prompt tokens | first differing token | share of the prompt | predicted | reused | result |",
             "|---|---|---|---|---|---|---|---|"]
    show = lambda v: "NOT MEASURABLE" if v is None else str(v)
    for t in report["trials"]:
        e = t["edited"]
        result = ("not evaluated" if t["match"] is None else "FAILED CONTROL: " + ", ".join(t["failures"]) if t["failures"]
                  else "not counted" if e["near_threshold"] else "match" if t["match"] else "MISMATCH")
        lines.append(f"| {t['repetition']} | {t['site']} | {e['n']} | {e['first_differing_token']} | "
                     f"{e['first_differing_token'] / e['n']:.4f} | {e['predicted_reuse']} | {show(e['cache_n'])} | {result} |")
    for x in report["unmeasurable"] + report["failures"] + report["mismatches"]:
        lines.append(f"- {x}")
    return "\n".join(lines) + "\n"


def summarize(run_id: str, repo_root: Path = REPO_ROOT) -> tuple[dict, str]:
    cfg = load_m1_config(repo_root / "config" / "m1.toml", repo_root)
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
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.summarize_m1")
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
