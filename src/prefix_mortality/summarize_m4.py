"""Idle expiry: recompute every trial from what is on disk, and refuse on any disagreement.

Nothing here talks to an engine. A trial is two requests under one nonce: an anchor, then, after a
gap of g seconds in which the driver sent nothing but one GET /props at the end, the anchor's bytes
again. At the pinned commit the server has one timer, --sleep-idle-seconds (default -1, off). Its
loop notes the time of the last task, shifted by the time the slots took, and once a second compares
it with the flag; when it sleeps it frees the contexts, and with them every slot and the prompt
cache, and the next request that needs the model reloads it with a new, empty cache. GET /props posts
no task: it neither moves the timer nor wakes the server, and it reports `is_sleeping`.

  no timer (the defaults):   predicted = n - 1 at every gap         server_sleeps = False
  timer S, gap g < S:        predicted = n - 1                      server_sleeps = False
  timer S, gap g > S:        predicted = 0                          server_sleeps = True

With nothing served between them, the anchor's slot keeps its prompt (ledger 0005: a slot is cleared
when another request launches), so the resend is an identical resend into a held slot: n - 1 (0003,
0004). The anchor itself is a control: a fresh prompt reuses 0 (0003, 0009). A registered gap keeps
a margin from S (config), and the recorded gap, from the anchor's last timestamp to the resend's
first, must be at least g and less than g plus that margin. The `is_sleeping` read after the gap must
agree with `server_sleeps`; a server that did not do what its flag says has failed a control, and so
has a run with any record between the two.

NOT MEASURABLE, never zero: a field the server did not report; no `is_sleeping` after the gap; a
record without a slot context; a request that does not fit it; unreadable timestamps; a trial during
which the local date changed (a chat template may carry the date).

A run's outcome is ALL MATCH, MISMATCH, FAILED CONTROL or NOT MEASURABLE. A verdict on a hypothesis
is stated by a ledger entry, from the outcomes of both models.
"""
import argparse
import json
import sys
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.clock import seconds_between
from prefix_mortality.config import M4Config, M4Hypothesis, load_m4_config
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.record import load_request, read
from prefix_mortality.summarize import FIELDS

ROLES = ("anchor", "resend")
CONFIGS = ("controls", "engines", "m4")
PREDICTION_KEYS = ("predicted_reuse", "server_sleeps")


def prediction(hyp: M4Hypothesis, gap: int, n_anchor: int) -> dict:
    """What the driver stores before it sends the resend, and what is recomputed here."""
    sleeps = hyp.sleeps and gap > hyp.sleep_idle_seconds
    return {"predicted_reuse": 0 if sleeps else n_anchor - 1, "server_sleeps": sleeps}


def _ctx(rec: dict):
    v = (rec.get("server") or {}).get("n_ctx")
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else None


def _sleeping(rec: dict):
    probe = rec.get("gap_probe")
    v = probe.get("is_sleeping") if isinstance(probe, dict) else None
    return v if isinstance(v, bool) else None


def _row(rec: dict, stored: dict) -> dict:
    o = rec["observed"]
    return {"role": rec["role"], "request_sha256": rec["request_sha256"], "nonce": rec["nonce"],
            "n": len(stored["tokens"]), **{f: o.get(f) for f in FIELDS}}


def evaluate_trial(anchor: dict, resend: dict, requests_dir: Path, cfg: M4Config, hyp: M4Hypothesis) -> dict:
    """One trial from its two records. `failures` are failed controls; `match` is the result."""
    recs = [anchor, resend]
    rows = [_row(r, load_request(requests_dir, r["request_sha256"])) for r in recs]
    gap = resend["gap_seconds"]
    out = {"repetition": resend["repetition"], "gap_seconds": gap, "observed_gap_seconds": None,
           "is_sleeping": _sleeping(resend), "failures": [], "unmeasurable": [], "match": None,
           "anchor": rows[0], "resend": rows[1]}
    for row in rows:
        missing = [f for f in FIELDS if row[f] is None]
        if missing:
            out["unmeasurable"].append(f"{row['role']}: the server reported no {', '.join(missing)}")
    ctxs = [_ctx(r) for r in recs]
    ctx = ctxs[0] if all(c is not None for c in ctxs) and len(set(ctxs)) == 1 else None
    if ctx is None:
        out["unmeasurable"].append("the server reported no slot context (n_ctx)")
    else:
        for row in rows:
            if row["n"] >= ctx:
                out["unmeasurable"].append(f"{row['role']}: a request of {row['n']} tokens does not fit the "
                                           f"slot context of {ctx} tokens")
    if len({r.get("local_date") for r in recs}) != 1:
        out["unmeasurable"].append("the local date changed during the trial (a chat template may carry the date)")
    if out["is_sleeping"] is None:
        out["unmeasurable"].append("resend: the server reported no is_sleeping after the gap")
    try:
        out["observed_gap_seconds"] = seconds_between(anchor["ts_end"], resend["ts_start"])
    except (KeyError, TypeError, ValueError):
        out["unmeasurable"].append("the records carry no readable timestamps around the gap")
    p = prediction(hyp, gap, rows[0]["n"])
    out["resend"].update(p)
    if out["unmeasurable"]:
        return out
    a, s, g = rows[0], rows[1], out["observed_gap_seconds"]
    checks = {"resend_is_the_anchor": s["request_sha256"] == a["request_sha256"] and s["nonce"] == a["nonce"],
              "nothing_between": isinstance(anchor.get("seq"), int) and resend.get("seq") == anchor["seq"] + 1,
              "gap_as_recorded": anchor.get("gap_seconds") == gap and gap <= g < gap + cfg.sleep_margin_seconds,
              "prediction_as_recorded": {key: resend.get(key) for key in PREDICTION_KEYS} == p,
              "sleep_state_as_predicted": out["is_sleeping"] == p["server_sleeps"],
              "anchor_reuses_0": a["cache_n"] == 0,
              "counts_add_up": all(r["cache_n"] + r["prompt_n"] == r["n"] for r in rows),
              "fields_agree": all(r["usage_cached_tokens"] == r["cache_n"] for r in rows)}
    out["failures"] = [key for key, ok in checks.items() if not ok]
    out["match"] = s["cache_n"] == p["predicted_reuse"]
    return out


def evaluate(records: list[dict], requests_dir: Path, cfg: M4Config) -> dict:
    if not records:
        raise ValueError("no record to evaluate")
    ids = {key: {r.get(key) for r in records} for key in ("run_id", "family", "hypothesis")}
    if any(len(v) != 1 for v in ids.values()):
        mixed = {key: sorted(map(str, v)) for key, v in ids.items()}
        raise ValueError(f"records mix runs, families or hypotheses: {mixed}")
    hid, family = ids["hypothesis"].pop(), ids["family"].pop()
    hyp = cfg.hypothesis(hid)
    slots = {(r.get("server") or {}).get("total_slots") for r in records}
    if slots != {hyp.slots}:
        raise ValueError(f"{hid} requires a server reporting {hyp.slots} slot(s); the records say "
                         f"{sorted(map(str, slots))}. This run is not that experiment")
    ctxs = {_ctx(r) for r in records} - {None}
    if len(ctxs) > 1:
        raise ValueError(f"records mix slot contexts {sorted(ctxs)}; this run is not one experiment")
    trials: dict[tuple[int, int], dict] = {}
    for r in records:
        if r.get("role") not in ROLES:
            raise ValueError(f"record {r.get('seq')}: unregistered role {r.get('role')!r}")
        if r.get("gap_seconds") not in hyp.gaps:
            raise ValueError(f"record {r.get('seq')}: a gap of {r.get('gap_seconds')!r} s is not registered for {hid}")
        got = trials.setdefault((r["repetition"], r["gap_seconds"]), {})
        if r["role"] in got:
            raise ValueError(f"repetition {r['repetition']} gap {r['gap_seconds']} s: repeated {r['role']} record")
        got[r["role"]] = r

    out, failures, unmeasurable, mismatches = [], [], [], []
    for rep, gap in sorted(trials):
        got, label = trials[(rep, gap)], f"repetition {rep} gap {gap} s"
        if set(got) != set(ROLES):
            failures.append(f"{label}: the records do not hold an anchor and a resend")
            continue
        t = evaluate_trial(got["anchor"], got["resend"], requests_dir, cfg, hyp)
        out.append(t)
        unmeasurable += [f"{label} {x}" for x in t["unmeasurable"]]
        failures += [f"{label}: {x} is false" for x in t["failures"]]
        if t["match"] is None or t["failures"]:
            continue
        if not t["match"]:
            mismatches.append(f"{label}: predicted {t['resend']['predicted_reuse']}, reused {t['resend']['cache_n']}")
    counted = [t for t in out if t["match"] is not None and not t["failures"]]
    by_gap = []
    for gap in hyp.gaps:
        ts = [t for t in counted if t["gap_seconds"] == gap]
        by_gap.append({"gap_seconds": gap, "counted": len(ts),
                       "kept": sum(t["resend"]["cache_n"] == t["resend"]["n"] - 1 for t in ts),
                       "lost": sum(t["resend"]["cache_n"] == 0 for t in ts),
                       "other": [t["resend"]["cache_n"] for t in ts
                                 if t["resend"]["cache_n"] not in (0, t["resend"]["n"] - 1)],
                       "slept": sum(bool(t["is_sleeping"]) for t in ts)})
    kept = [t["gap_seconds"] for t in counted if t["resend"]["cache_n"] == t["resend"]["n"] - 1]
    lost = [t["gap_seconds"] for t in counted if t["resend"]["cache_n"] == 0]
    other = [[t["gap_seconds"], t["resend"]["cache_n"]] for t in counted
             if t["resend"]["cache_n"] not in (0, t["resend"]["n"] - 1)]
    outcome = ("NOT MEASURABLE" if unmeasurable else "FAILED CONTROL" if failures
               else "MISMATCH" if mismatches else "ALL MATCH")
    return {"run_id": ids["run_id"].pop(), "family": family, "hypothesis": hid, "slots": hyp.slots,
            "sleep_idle_seconds": hyp.sleep_idle_seconds, "gaps": list(hyp.gaps),
            "sleep_margin_seconds": cfg.sleep_margin_seconds, "trials": out, "by_gap": by_gap,
            "unmeasurable": unmeasurable, "failures": failures, "mismatches": mismatches,
            "bracket": {"largest_gap_kept": max(kept) if kept else None,
                        "smallest_gap_lost": min(lost) if lost else None, "other_readings": other},
            "outcome": outcome}


def render(report: dict) -> str:
    counted = [t for t in report["trials"] if t["match"] is not None and not t["failures"]]
    b = report["bracket"]
    show = lambda v: "NOT MEASURABLE" if v is None else str(v)
    none = lambda v: "none" if v is None else str(v)
    timer = ("no timer" if report["sleep_idle_seconds"] < 0
             else f"--sleep-idle-seconds {report['sleep_idle_seconds']}")
    lines = [f"m4 {report['run_id']} ({report['family']}, {report['hypothesis']}, {report['slots']} slot(s), "
             f"{timer}): {report['outcome']}",
             f"trials counted: {len(counted)}; matching: {sum(t['match'] for t in counted)}; "
             f"largest gap kept: {none(b['largest_gap_kept'])}; smallest gap lost: {none(b['smallest_gap_lost'])}", "",
             "| rep | gap s | observed gap s | anchor tokens | sleeping after the gap | predicted | reused | result |",
             "|---|---|---|---|---|---|---|---|"]
    for t in report["trials"]:
        s = t["resend"]
        result = ("not evaluated" if t["match"] is None else "FAILED CONTROL: " + ", ".join(t["failures"]) if t["failures"]
                  else "match" if t["match"] else "MISMATCH")
        og = t["observed_gap_seconds"]
        shown_gap = "NOT MEASURABLE" if og is None else f"{og:.1f}"
        lines.append(f"| {t['repetition']} | {t['gap_seconds']} | {shown_gap} | {s['n']} | {show(t['is_sleeping'])} | "
                     f"{s['predicted_reuse']} | {show(s['cache_n'])} | {result} |")
    for x in report["unmeasurable"] + report["failures"] + report["mismatches"]:
        lines.append(f"- {x}")
    return "\n".join(lines) + "\n"


def summarize(run_id: str, repo_root: Path = REPO_ROOT) -> tuple[dict, str]:
    cfg = load_m4_config(repo_root / "config" / "m4.toml", repo_root)
    records = read(cfg.corpus_dir / f"{run_id}.jsonl")
    current = {key: sha256_text_file(repo_root / "config" / f"{key}.toml") for key in CONFIGS}
    for r in records:
        if r.get("config_sha256") != current:
            raise ValueError(f"record {r.get('seq')} was written under a different config than the one on disk")
    rp = cfg.results_dir / run_id / "report.json"
    if not rp.exists():
        raise ValueError(f"{rp} does not exist; the driver wrote no report for this run")
    recorded = json.loads(rp.read_text(encoding="utf-8"))
    report = evaluate(records, repo_root / "corpus" / "requests", cfg)
    if report != recorded:
        diff = sorted(key for key in set(report) | set(recorded) if report.get(key) != recorded.get(key))
        raise ValueError(f"the records do not reproduce the driver's report; differing keys: {diff}")
    text = render(report)
    (cfg.results_dir / run_id / "summary.md").write_text(text, encoding="utf-8", newline="\n")
    return report, text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.summarize_m4")
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
