"""Rebuild: recompute every trial from what is on disk, and refuse on any disagreement.

Nothing here talks to an engine. A trial is two requests under one fresh nonce: a recorded
conversation replayed in full at its last assistant turn, then the same conversation compacted — the
messages from the first user message up to the midpoint cut removed (`trim`) or replaced by one
registered summary message (`summary`). The compacted request's predicted reuse is a function of the
two stored token lists and the registered constants, under the hypothesis's rule:

  prefix     d, the tokens the two share from the start (one slot: 0010)
  threshold  d when d / n is above the similarity threshold, else 0 (the defaults: 0010)
  walk       d plus every later run of at least cache_reuse_n matching tokens, shifted into place
             (--cache-reuse, server-context.cpp 3262-3290 at the pin), one below n when wholly held

The driver writes the prediction, with the walk's chunk list, before the compacted request is sent;
this module recomputes it and refuses a record that carries another value. Controls inside the trial:
the full request reuses at most the tokens before its nonce (a fresh prompt, as 0003 and 0009); the two
requests share the nonce and differ in bytes; nothing lies between them; every request's two counts add
up to its token count and its two reuse fields agree. A threshold trial within the registered margin of
the threshold is reported and not counted (0006). NOT MEASURABLE, never zero: a field the server did not
report, no slot context, a request that does not fit it, a local date that changed inside the trial.
"""
import argparse
import json
import sys
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import M5Config, load_m5_config
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.record import load_request, read
from prefix_mortality.recorded import SIMULATIONS, load as load_recorded
from prefix_mortality.replay import longest
from prefix_mortality.slotsim import Token, cache_reuse_walk, lcp, tokens
from prefix_mortality.summarize import FIELDS, header_tokens
from prefix_mortality.summarize_m1 import near_threshold, predict

CONFIGS = ("controls", "engines", "m5")
ROLES = ("full", "compacted")
PREDICTION_KEYS = ("first_differing_token", "predicted_reuse", "near_threshold", "chunks", "shifted")


def prediction(cfg: M5Config, hid: str, full: list[Token], compacted: list[Token]) -> dict:
    """What the driver stores before it sends the compacted request, and what is recomputed here."""
    rule = cfg.hypothesis(hid).rule
    d, n = lcp(full, compacted), len(compacted)
    if rule == "walk":
        n_past, chunks = cache_reuse_walk(full, compacted, cfg.cache_reuse_n)
        return {"first_differing_token": d, "predicted_reuse": min(n_past, n - 1), "near_threshold": False,
                "chunks": [list(c) for c in chunks], "shifted": sum(c[2] for c in chunks)}
    return {"first_differing_token": d, "predicted_reuse": min(predict(rule, d, n, cfg.similarity_threshold), n - 1),
            "near_threshold": near_threshold(rule, d, n, cfg.similarity_threshold, cfg.threshold_margin),
            "chunks": [], "shifted": 0}


def _toks(stored: dict) -> list[Token]:
    return tokens([t["id"] for t in stored["tokens"]], [t["piece"] for t in stored["tokens"]])


def _ctx(rec: dict):
    v = (rec.get("server") or {}).get("n_ctx")
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else None


def evaluate_trial(full: dict, compacted: dict, requests_dir: Path, cfg: M5Config, hid: str) -> dict:
    """One trial from its two records. `failures` are failed controls; `match` is the result, None
    when the trial is not counted."""
    recs = {"full": full, "compacted": compacted}
    stored = {role: load_request(requests_dir, r["request_sha256"]) for role, r in recs.items()}
    toks = {role: _toks(s) for role, s in stored.items()}
    out = {"conversation": compacted["conversation"], "arm": compacted["arm"], "nonce": compacted["nonce"],
           "cut_index": compacted.get("cut_index"), "failures": [], "unmeasurable": [], "match": None}
    rows = {}
    for role, r in recs.items():
        o = r["observed"]
        rows[role] = {"request_sha256": r["request_sha256"], "n": len(toks[role]),
                      "h": header_tokens(stored[role]["tokens"], r["nonce"]), **{f: o.get(f) for f in FIELDS}}
        missing = [f for f in FIELDS if rows[role][f] is None]
        if missing:
            out["unmeasurable"].append(f"{role}: the server reported no {', '.join(missing)}")
    p = prediction(cfg, hid, toks["full"], toks["compacted"])
    rows["compacted"].update(p)
    out.update({"full": rows["full"], "compacted": rows["compacted"]})
    ctxs = [_ctx(r) for r in recs.values()]
    ctx = ctxs[0] if all(c is not None for c in ctxs) and len(set(ctxs)) == 1 else None
    if ctx is None:
        out["unmeasurable"].append("the server reported no slot context (n_ctx)")
    else:
        for role, row in rows.items():
            if row["n"] >= ctx:
                out["unmeasurable"].append(f"{role}: a request of {row['n']} tokens does not fit the slot context "
                                           f"of {ctx} tokens")
    if len({r.get("local_date") for r in recs.values()}) != 1:
        out["unmeasurable"].append("the local date changed during the trial (a chat template may carry the date)")
    if out["unmeasurable"]:
        return out
    f, c = rows["full"], rows["compacted"]
    checks = {"same_nonce": full["nonce"] == compacted["nonce"],
              "compacted_differs_in_bytes": f["request_sha256"] != c["request_sha256"],
              "nothing_between": isinstance(full.get("seq"), int) and compacted.get("seq") == full["seq"] + 1,
              "prediction_as_recorded": {k: compacted.get(k) for k in PREDICTION_KEYS} == p,
              "full_reuses_at_most_its_header": f["cache_n"] <= f["h"],
              "counts_add_up": all(r["cache_n"] + r["prompt_n"] == r["n"] for r in rows.values()),
              "fields_agree": all(r["usage_cached_tokens"] == r["cache_n"] for r in rows.values())}
    out["failures"] = [k for k, ok in checks.items() if not ok]
    if not p["near_threshold"]:
        out["match"] = c["cache_n"] == p["predicted_reuse"]
    return out


def evaluate(records: list[dict], requests_dir: Path, cfg: M5Config) -> dict:
    if not records:
        raise ValueError("no record to evaluate")
    ids = {key: {r.get(key) for r in records} for key in ("run_id", "family", "hypothesis", "recorded_sha256")}
    if any(len(v) != 1 for v in ids.values()):
        mixed = {key: sorted(map(str, v)) for key, v in ids.items()}
        raise ValueError(f"records mix runs, families, hypotheses or corpora: {mixed}")
    hid, family = ids["hypothesis"].pop(), ids["family"].pop()
    hyp = cfg.hypothesis(hid)
    slots = {(r.get("server") or {}).get("total_slots") for r in records}
    if slots != {hyp.slots}:
        raise ValueError(f"{hid} requires a server reporting {hyp.slots} slot(s); the records say "
                         f"{sorted(map(str, slots))}. This run is not that experiment")
    ctxs = {_ctx(r) for r in records} - {None}
    if len(ctxs) > 1:
        raise ValueError(f"records mix slot contexts {sorted(ctxs)}; this run is not one experiment")
    sims, prov = load_recorded(cfg.recorded_dir)
    if ids["recorded_sha256"].pop() != prov["output"][SIMULATIONS]["sha256"]:
        raise ValueError("the records name a recorded corpus other than the one on disk")
    registered = {s["task_id"] for s in longest(sims, cfg.conversations)}
    trials: dict[tuple[str, str], dict] = {}
    for r in records:
        if r.get("role") not in ROLES:
            raise ValueError(f"record {r.get('seq')}: unregistered role {r.get('role')!r}")
        if r.get("arm") not in cfg.arms:
            raise ValueError(f"record {r.get('seq')}: unregistered arm {r.get('arm')!r}")
        if r.get("conversation") not in registered:
            raise ValueError(f"record {r.get('seq')}: conversation {r.get('conversation')!r} is not one of the "
                             f"{cfg.conversations} longest; this run is not that experiment")
        got = trials.setdefault((r["conversation"], r["arm"]), {})
        if r["role"] in got:
            raise ValueError(f"conversation {r['conversation']} arm {r['arm']}: repeated {r['role']} record")
        got[r["role"]] = r

    out, failures, unmeasurable, mismatches = [], [], [], []
    for key in sorted(trials, key=lambda k: trials[k][next(iter(trials[k]))]["seq"]):
        got, label = trials[key], f"conversation {key[0]} arm {key[1]}"
        if set(got) != set(ROLES):
            failures.append(f"{label}: the records do not hold a full and a compacted request")
            continue
        t = evaluate_trial(got["full"], got["compacted"], requests_dir, cfg, hid)
        out.append(t)
        unmeasurable += [f"{label} {x}" for x in t["unmeasurable"]]
        failures += [f"{label}: {x} is false" for x in t["failures"]]
        if t["match"] is False and not t["failures"]:
            mismatches.append(f"{label}: predicted {t['compacted']['predicted_reuse']}, reused {t['compacted']['cache_n']}")
    counted = [t for t in out if t["match"] is not None and not t["failures"]]
    by_arm = []
    for arm in cfg.arms:
        ts = [t for t in out if t["arm"] == arm]
        cs = [t for t in counted if t["arm"] == arm]
        by_arm.append({"arm": arm, "trials": len(ts), "counted": len(cs), "matching": sum(t["match"] for t in cs),
                       "near_threshold": sum(bool(t["compacted"].get("near_threshold")) for t in ts),
                       "shifted_total": sum(t["compacted"].get("shifted") or 0 for t in ts),
                       "reused": [t["compacted"]["cache_n"] for t in ts]})
    outcome = ("NOT MEASURABLE" if unmeasurable else "FAILED CONTROL" if failures
               else "MISMATCH" if mismatches else "ALL MATCH")
    return {"run_id": ids["run_id"].pop(), "family": family, "hypothesis": hid, "slots": hyp.slots, "rule": hyp.rule,
            "cache_reuse_n": cfg.cache_reuse_n if hyp.rule == "walk" else 0, "trials": out, "by_arm": by_arm,
            "counts": {"trials": len(out), "counted": len(counted), "matching": sum(t["match"] for t in counted)},
            "unmeasurable": unmeasurable, "failures": failures, "mismatches": mismatches, "outcome": outcome}


def render(report: dict) -> str:
    k = report["counts"]
    show = lambda v: "NOT MEASURABLE" if v is None else str(v)
    reuse = {"prefix": "--parallel 1", "threshold": "defaults", "walk": f"--parallel 1 --cache-reuse {report['cache_reuse_n']}"}
    lines = [f"m5 {report['run_id']} ({report['family']}, {report['hypothesis']}, {report['slots']} slot(s), "
             f"{reuse[report['rule']]}): {report['outcome']}",
             f"trials: {k['trials']}; counted: {k['counted']}; matching: {k['matching']}", "",
             "| conversation | arm | n full | n compacted | d | d / n | shifted | predicted | reused | result |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for t in report["trials"]:
        c = t["compacted"]
        result = ("not evaluated" if t["match"] is None and not t["failures"] and not c.get("near_threshold")
                  else "near threshold, not counted" if c.get("near_threshold")
                  else "FAILED CONTROL: " + ", ".join(t["failures"]) if t["failures"]
                  else "match" if t["match"] else "MISMATCH")
        share = f"{c['first_differing_token'] / c['n']:.4f}" if c.get("n") else "NOT MEASURABLE"
        lines.append(f"| {t['conversation']} | {t['arm']} | {t['full']['n']} | {c['n']} | {c['first_differing_token']} | "
                     f"{share} | {c.get('shifted', 0)} | {c['predicted_reuse']} | {show(c['cache_n'])} | {result} |")
    for x in report["unmeasurable"] + report["failures"] + report["mismatches"]:
        lines.append(f"- {x}")
    return "\n".join(lines) + "\n"


def summarize(run_id: str, repo_root: Path = REPO_ROOT) -> tuple[dict, str]:
    cfg = load_m5_config(repo_root / "config" / "m5.toml", repo_root)
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
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.summarize_m5")
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
