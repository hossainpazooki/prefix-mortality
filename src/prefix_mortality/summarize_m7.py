"""Eviction by intervening requests: recompute every trial from what is on disk, and refuse on any
disagreement.

Nothing here talks to an engine. A trial is K + 2 requests: an anchor under a fresh nonce, K foreign
requests (the same base request, each under its own fresh nonce) served one at a time, then the
anchor again byte for byte. At the server's defaults the anchor's slot is cleared when the first
foreign request starts, and the anchor survives only as a copy in the server's RAM prompt cache,
which keeps entries in arrival order under a size limit and drops the oldest until a new entry fits.
When the resend arrives the K-th foreign prompt is still in its slot, so the cache has been asked to
hold the anchor and the first K - 1 foreign prompts together:

  state(r)  = n_r x bytes per token, from the registered KV geometry of the model
  fits      = state(anchor) + sum of state(foreign_i) for i < K  <=  cache_ram_mib x 2^20
  predicted = n_anchor - 1 if fits, else 0

(an identical resend reuses n - 1: ledger 0003, 0004). The anchor and every foreign request are held
to the defaults' measured rule for a fresh prompt, reuse exactly 0 (ledger 0003, 0009); a nonzero
there means the trial was not isolated and the run has failed a control. The source has a second
eviction pass on a token total, max(n_ctx, limit / mean bytes per token); it is computed here from
the recorded slot context and reported per trial as what bound, and never used for the prediction.

NOT MEASURABLE, never zero: a field the server did not report; a record without a slot context; a
request that does not fit the slot context (the server refuses such a request); a trial during which
the local date changed (a chat template may carry the date).

A run's outcome is ALL MATCH, MISMATCH, FAILED CONTROL or NOT MEASURABLE. A verdict on a hypothesis
is stated by a ledger entry, from the outcomes of both models.
"""
import argparse
import json
import sys
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import M7Config, load_m7_config
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.record import load_request, read
from prefix_mortality.summarize import FIELDS

ROLES = ("anchor", "foreign", "resend")
CONFIGS = ("controls", "engines", "m7")
PREDICTION_KEYS = ("predicted_reuse", "modelled_cache_tokens", "modelled_cache_bytes", "fits_size_limit")


def prediction(cfg: M7Config, family: str, n_anchor: int, n_foreign: list[int]) -> dict:
    """What the driver stores before it sends the resend, and what is recomputed here. `n_foreign`
    holds the token counts of the K foreign prompts in the order they are sent."""
    k = len(n_foreign)
    tokens = n_anchor + sum(n_foreign[:max(k - 1, 0)])
    size = tokens * cfg.bytes_per_token(family)
    fits = size <= cfg.cache_limit_bytes
    return {"predicted_reuse": n_anchor - 1 if fits else 0, "modelled_cache_tokens": tokens,
            "modelled_cache_bytes": size, "fits_size_limit": fits}


def token_pass(cfg: M7Config, family: str, modelled_cache_tokens: int, n_ctx: int) -> dict:
    """The source's second pass, a diagnostic: the token total against max(n_ctx, limit / bytes per token)."""
    limit = max(n_ctx, cfg.cache_limit_bytes // cfg.bytes_per_token(family))
    return {"token_limit": limit, "fits_token_limit": modelled_cache_tokens <= limit}


def bound_by(fits_size: bool, fits_tokens: bool) -> str:
    return {(True, True): "neither", (False, True): "size", (True, False): "tokens",
            (False, False): "size and tokens"}[(fits_size, fits_tokens)]


def _ctx(rec: dict):
    v = (rec.get("server") or {}).get("n_ctx")
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else None


def _name(row: dict) -> str:
    return f"foreign {row['index']}" if row["role"] == "foreign" else row["role"]


def _row(rec: dict, stored: dict) -> dict:
    o = rec["observed"]
    return {"role": rec["role"], "index": rec.get("index"), "request_sha256": rec["request_sha256"],
            "nonce": rec["nonce"], "n": len(stored["tokens"]), **{f: o.get(f) for f in FIELDS}}


def evaluate_trial(anchor: dict, foreign: list[dict], resend: dict, requests_dir: Path, cfg: M7Config) -> dict:
    """One trial from its K + 2 records. `failures` are failed controls; `match` is the result."""
    k = len(foreign)
    recs = [anchor, *foreign, resend]
    rows = [_row(r, load_request(requests_dir, r["request_sha256"])) for r in recs]
    out = {"repetition": resend["repetition"], "k": k, "failures": [], "unmeasurable": [], "match": None,
           "bound_by": None, "anchor": rows[0], "foreign": rows[1:-1], "resend": rows[-1]}
    for row in rows:
        missing = [f for f in FIELDS if row[f] is None]
        if missing:
            out["unmeasurable"].append(f"{_name(row)}: the server reported no {', '.join(missing)}")
    ctxs = [_ctx(r) for r in recs]
    ctx = ctxs[0] if all(c is not None for c in ctxs) and len(set(ctxs)) == 1 else None
    if ctx is None:
        out["unmeasurable"].append("the server reported no slot context (n_ctx)")
    else:
        for row in rows:
            if row["n"] >= ctx:
                out["unmeasurable"].append(f"{_name(row)}: a request of {row['n']} tokens does not fit the "
                                           f"slot context of {ctx} tokens")
    if len({r.get("local_date") for r in recs}) != 1:
        out["unmeasurable"].append("the local date changed during the trial (a chat template may carry the date)")
    p = prediction(cfg, anchor["family"], rows[0]["n"], [r["n"] for r in rows[1:-1]])
    out["resend"].update(p)
    if ctx is not None:
        tp = token_pass(cfg, anchor["family"], p["modelled_cache_tokens"], ctx)
        out["resend"].update(tp)
        out["bound_by"] = bound_by(p["fits_size_limit"], tp["fits_token_limit"])
    if out["unmeasurable"]:
        return out
    a, fs, s = rows[0], rows[1:-1], rows[-1]
    checks = {"resend_is_the_anchor": s["request_sha256"] == a["request_sha256"] and s["nonce"] == a["nonce"],
              "nonces_distinct": len({a["nonce"], *(f["nonce"] for f in fs)}) == k + 1,
              "k_as_recorded": all(r.get("k") == k for r in recs) and [f["index"] for f in fs] == list(range(1, k + 1)),
              "prediction_as_recorded": {key: resend.get(key) for key in PREDICTION_KEYS} == p,
              "anchor_reuses_0": a["cache_n"] == 0,
              "foreign_reuse_0": all(f["cache_n"] == 0 for f in fs),
              "counts_add_up": all(r["cache_n"] + r["prompt_n"] == r["n"] for r in rows),
              "fields_agree": all(r["usage_cached_tokens"] == r["cache_n"] for r in rows)}
    out["failures"] = [key for key, ok in checks.items() if not ok]
    out["match"] = s["cache_n"] == p["predicted_reuse"]
    return out


def evaluate(records: list[dict], requests_dir: Path, cfg: M7Config) -> dict:
    if not records:
        raise ValueError("no record to evaluate")
    ids = {key: {r.get(key) for r in records} for key in ("run_id", "family", "hypothesis")}
    if any(len(v) != 1 for v in ids.values()):
        mixed = {key: sorted(map(str, v)) for key, v in ids.items()}
        raise ValueError(f"records mix runs, families or hypotheses: {mixed}")
    hid, family = ids["hypothesis"].pop(), ids["family"].pop()
    hyp = cfg.hypothesis(hid)
    cfg.geometry(family)
    slots = {(r.get("server") or {}).get("total_slots") for r in records}
    if slots != {hyp.slots}:
        raise ValueError(f"{hid} requires a server reporting {hyp.slots} slot(s); the records say {sorted(map(str, slots))}. "
                         "This run is not that experiment")
    ctxs = {_ctx(r) for r in records} - {None}
    if len(ctxs) > 1:
        raise ValueError(f"records mix slot contexts {sorted(ctxs)}; this run is not one experiment")
    trials: dict[tuple[int, int], dict] = {}
    for r in records:
        if r.get("role") not in ROLES:
            raise ValueError(f"record {r.get('seq')}: unregistered role {r.get('role')!r}")
        if r.get("k") not in cfg.k_schedule:
            raise ValueError(f"record {r.get('seq')}: K = {r.get('k')!r} is not in the registered schedule")
        got = trials.setdefault((r["repetition"], r["k"]), {"foreign": {}})
        if r["role"] == "foreign":
            if r.get("index") in got["foreign"]:
                raise ValueError(f"repetition {r['repetition']} K={r['k']}: repeated foreign record {r.get('index')}")
            got["foreign"][r.get("index")] = r
        else:
            if r["role"] in got:
                raise ValueError(f"repetition {r['repetition']} K={r['k']}: repeated {r['role']} record")
            got[r["role"]] = r

    out, failures, unmeasurable, mismatches = [], [], [], []
    for rep, k in sorted(trials):
        got, label = trials[(rep, k)], f"repetition {rep} K={k}"
        if "anchor" not in got or "resend" not in got or set(got["foreign"]) != set(range(1, k + 1)):
            failures.append(f"{label}: the records do not hold an anchor, K foreign requests and a resend")
            continue
        t = evaluate_trial(got["anchor"], [got["foreign"][i] for i in range(1, k + 1)], got["resend"], requests_dir, cfg)
        out.append(t)
        unmeasurable += [f"{label} {x}" for x in t["unmeasurable"]]
        failures += [f"{label}: {x} is false" for x in t["failures"]]
        if t["match"] is None or t["failures"]:
            continue
        if not t["match"]:
            mismatches.append(f"{label}: predicted {t['resend']['predicted_reuse']}, reused {t['resend']['cache_n']}")
    counted = [t for t in out if t["match"] is not None and not t["failures"]]
    kept = [t["k"] for t in counted if t["resend"]["cache_n"] == t["resend"]["n"] - 1]
    lost = [t["k"] for t in counted if t["resend"]["cache_n"] == 0]
    other = [[t["k"], t["resend"]["cache_n"]] for t in counted if t["k"] not in kept and t["k"] not in lost]
    outcome = ("NOT MEASURABLE" if unmeasurable else "FAILED CONTROL" if failures
               else "MISMATCH" if mismatches else "ALL MATCH")
    return {"run_id": ids["run_id"].pop(), "family": family, "hypothesis": hid, "slots": hyp.slots,
            "cache_ram_mib": cfg.cache_ram_mib, "bytes_per_token": cfg.bytes_per_token(family),
            "k_schedule": list(cfg.k_schedule), "trials": out, "unmeasurable": unmeasurable, "failures": failures,
            "mismatches": mismatches,
            "bracket": {"largest_k_kept": max(kept) if kept else None, "smallest_k_lost": min(lost) if lost else None,
                        "other_readings": other},
            "outcome": outcome}


def render(report: dict) -> str:
    counted = [t for t in report["trials"] if t["match"] is not None and not t["failures"]]
    b = report["bracket"]
    show = lambda v: "NOT MEASURABLE" if v is None else str(v)
    lines = [f"m7 {report['run_id']} ({report['family']}, {report['hypothesis']}, {report['slots']} slot(s), "
             f"cache {report['cache_ram_mib']} MiB, {report['bytes_per_token']} bytes per token): {report['outcome']}",
             f"trials counted: {len(counted)}; matching: {sum(t['match'] for t in counted)}; "
             f"largest K kept: {show(b['largest_k_kept'])}; smallest K lost: {show(b['smallest_k_lost'])}", "",
             "| rep | K | anchor tokens | modelled cache tokens | modelled cache MiB | fits size limit | bound by | predicted | reused | result |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for t in report["trials"]:
        s = t["resend"]
        result = ("not evaluated" if t["match"] is None else "FAILED CONTROL: " + ", ".join(t["failures"]) if t["failures"]
                  else "match" if t["match"] else "MISMATCH")
        lines.append(f"| {t['repetition']} | {t['k']} | {s['n']} | {s['modelled_cache_tokens']} | "
                     f"{s['modelled_cache_bytes'] / 2**20:.1f} | {'yes' if s['fits_size_limit'] else 'no'} | "
                     f"{show(t['bound_by'])} | {s['predicted_reuse']} | {show(s['cache_n'])} | {result} |")
    for x in report["unmeasurable"] + report["failures"] + report["mismatches"]:
        lines.append(f"- {x}")
    return "\n".join(lines) + "\n"


def summarize(run_id: str, repo_root: Path = REPO_ROOT) -> tuple[dict, str]:
    cfg = load_m7_config(repo_root / "config" / "m7.toml", repo_root)
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
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.summarize_m7")
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
