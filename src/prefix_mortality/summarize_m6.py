"""Model switch and restart: recompute every trial from what is on disk, and refuse on any disagreement.

Nothing here talks to an engine. Two kinds of trial, each under one fresh nonce, the bodies the base
request of config/controls.toml with a `model` field naming the child.

Router (`H-M6LA`, `H-M6LB`): three requests — the anchor to child A (the family under test), the
anchor's messages to child B (a second, small model), the anchor's bytes to A again. The router
forwards each to the child its body names (server.cpp 205-248); B is another process and has never
seen the prompt; A keeps its slots while it stays loaded, and `--models-max` unloads the least
recently used idle child when another must load (server-models.cpp 264-384, 1074-1090).

  --models-max 4:  A, B and A again all loaded          resend reuses n_A - 1 (0003: the slot held)
  --models-max 1:  loading B unloads A; A again reloads  resend reuses 0 (a fresh process)

Restart (`H-M6LR`): a single server, one slot, `--slot-save-path`. Part `restart`: anchor; the
process is stopped and started; resend reuses 0. Part `save-restore`: anchor; `POST
/slots/0?action=save`; stop and start; `action=restore`; resend reuses n - 1 (server-context.cpp
2606-2665: the restore sets the slot's tokens and state from the file).

Controls: the anchor, and B's request, reuse at most the tokens before their nonce (a fresh prompt,
0003/0009); the resend is the anchor's bytes; nothing lies between the trial's requests; every response
names the child that answered, and the loaded set the router reported before each request is what
the cell requires (A and B loaded at the resend under `--models-max 4`; A not loaded at the resend
under `--models-max 1`); a restart raises the process generation by one and the save and restore
report the anchor's token count; every request's two counts add up and its reuse fields agree. NOT
MEASURABLE, never zero: a field the server did not report, no slot context, a request that does not
fit it, the local date changing inside a trial.
"""
import argparse
import json
import sys
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import M6Config, M6Hypothesis, load_m6_config
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.record import load_request, read
from prefix_mortality.summarize import FIELDS, header_tokens

CONFIGS = ("controls", "engines", "m6")
ROUTER_ROLES = ("anchor", "other", "resend")
RESTART_ROLES = ("anchor", "resend")
PARTS = ("restart", "save-restore")


def prediction(hyp: M6Hypothesis, part: str | None, n_anchor: int) -> int:
    """The resend's predicted reuse from the cell and the anchor's token count."""
    if hyp.mode == "router":
        return n_anchor - 1 if hyp.models_max > 1 else 0
    return n_anchor - 1 if part == "save-restore" else 0


def _ctx(rec: dict):
    v = (rec.get("server") or {}).get("n_ctx")
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else None


def _row(rec: dict, stored: dict) -> dict:
    o = rec["observed"]
    return {"role": rec["role"], "child": rec.get("child"), "response_model": rec.get("response_model"),
            "request_sha256": rec["request_sha256"], "n": len(stored["tokens"]),
            "h": header_tokens(stored["tokens"], rec["nonce"]), "loaded_before": rec.get("loaded_before"),
            "process": rec.get("process"), **{f: o.get(f) for f in FIELDS}}


def evaluate_trial(recs: dict, requests_dir: Path, hyp: M6Hypothesis, child_a: str, child_b: str) -> dict:
    """One trial from its records by role. `failures` are failed controls; `match` is the result."""
    roles = ROUTER_ROLES if hyp.mode == "router" else RESTART_ROLES
    rows = {role: _row(recs[role], load_request(requests_dir, recs[role]["request_sha256"])) for role in roles}
    resend = recs["resend"]
    out = {"repetition": resend["repetition"], "part": resend.get("part"), "nonce": resend["nonce"],
           "failures": [], "unmeasurable": [], "match": None, **rows}
    for role, row in rows.items():
        missing = [f for f in FIELDS if row[f] is None]
        if missing:
            out["unmeasurable"].append(f"{role}: the server reported no {', '.join(missing)}")
    ctx_a = [_ctx(recs[r]) for r in roles if r != "other"]
    ctx = ctx_a[0] if all(c is not None for c in ctx_a) and len(set(ctx_a)) == 1 else None
    if ctx is None:
        out["unmeasurable"].append("child A reported no slot context (n_ctx)")
    else:
        for role in roles:
            if role != "other" and rows[role]["n"] >= ctx:
                out["unmeasurable"].append(f"{role}: a request of {rows[role]['n']} tokens does not fit the slot "
                                           f"context of {ctx} tokens")
    if len({recs[r].get("local_date") for r in roles}) != 1:
        out["unmeasurable"].append("the local date changed during the trial (a chat template may carry the date)")
    p = prediction(hyp, resend.get("part"), rows["anchor"]["n"])
    out["resend"]["predicted_reuse"] = p
    if out["unmeasurable"]:
        return out
    a, s = rows["anchor"], rows["resend"]
    seqs = [recs[r]["seq"] for r in roles]
    checks = {"same_nonce": len({recs[r]["nonce"] for r in roles}) == 1,
              "resend_is_the_anchor": s["request_sha256"] == a["request_sha256"],
              "nothing_between": seqs == list(range(seqs[0], seqs[0] + len(roles))),
              "prediction_as_recorded": resend.get("predicted_reuse") == p,
              "anchor_reuses_at_most_its_header": a["cache_n"] <= a["h"],
              "counts_add_up": all(r["cache_n"] + r["prompt_n"] == r["n"] for r in rows.values()),
              "fields_agree": all(r["usage_cached_tokens"] == r["cache_n"] for r in rows.values()),
              "anchor_and_resend_to_child_a": a["child"] == s["child"] == child_a}
    if hyp.mode == "router":
        o = rows["other"]
        loaded_resend = set(s["loaded_before"] or [])
        # the router's children answer under their names; a single server answers under its own alias
        checks.update({"children_as_named": all(r["response_model"] == r["child"] for r in rows.values()),
                       "other_goes_to_child_b": o["child"] == child_b and o["request_sha256"] != a["request_sha256"],
                       "other_reuses_at_most_its_header": o["cache_n"] <= o["h"],
                       "loaded_set_as_the_cell_requires":
                           ({child_a, child_b} <= loaded_resend) if hyp.models_max > 1
                           else (child_a not in loaded_resend and len(loaded_resend) <= 1
                                 and all(len(set(r["loaded_before"] or [])) <= 1 for r in rows.values()))})
    else:
        ga, gs = (a["process"] or {}).get("generation"), (s["process"] or {}).get("generation")
        checks["process_restarted_once"] = isinstance(ga, int) and gs == ga + 1
        if resend.get("part") == "save-restore":
            saved, restored = resend.get("slot_save") or {}, resend.get("slot_restore") or {}
            checks["slot_saved_and_restored_whole"] = (saved.get("n_saved") == a["n"] and restored.get("n_restored") == a["n"])
        else:
            checks["no_slot_action"] = not resend.get("slot_save") and not resend.get("slot_restore")
    out["failures"] = [k for k, ok in checks.items() if not ok]
    out["match"] = s["cache_n"] == p
    return out


def evaluate(records: list[dict], requests_dir: Path, cfg: M6Config) -> dict:
    if not records:
        raise ValueError("no record to evaluate")
    ids = {key: {r.get(key) for r in records} for key in ("run_id", "family", "hypothesis")}
    if any(len(v) != 1 for v in ids.values()):
        mixed = {key: sorted(map(str, v)) for key, v in ids.items()}
        raise ValueError(f"records mix runs, families or hypotheses: {mixed}")
    hid, family = ids["hypothesis"].pop(), ids["family"].pop()
    hyp = cfg.hypothesis(hid)
    child_a, child_b = family, cfg.child_b.family
    roles = ROUTER_ROLES if hyp.mode == "router" else RESTART_ROLES
    slots_a = {(r.get("server") or {}).get("total_slots") for r in records if r.get("role") != "other"}
    if slots_a != {hyp.slots}:
        raise ValueError(f"{hid} requires child A reporting {hyp.slots} slot(s); the records say "
                         f"{sorted(map(str, slots_a))}. This run is not that experiment")
    ctxs = {_ctx(r) for r in records if r.get("role") != "other"} - {None}
    if len(ctxs) > 1:
        raise ValueError(f"records mix slot contexts {sorted(ctxs)}; this run is not one experiment")
    trials: dict[tuple, dict] = {}
    for r in records:
        if r.get("role") not in roles:
            raise ValueError(f"record {r.get('seq')}: unregistered role {r.get('role')!r} for a {hyp.mode} cell")
        part = r.get("part")
        if hyp.mode == "restart" and part not in PARTS:
            raise ValueError(f"record {r.get('seq')}: unregistered part {part!r}")
        if hyp.mode == "router" and part is not None:
            raise ValueError(f"record {r.get('seq')}: a router cell has no parts")
        if r.get("repetition") not in range(1, cfg.repetitions + 1):
            raise ValueError(f"record {r.get('seq')}: repetition {r.get('repetition')!r} is not registered")
        got = trials.setdefault((r["repetition"], part), {})
        if r["role"] in got:
            raise ValueError(f"repetition {r['repetition']} {part or ''}: repeated {r['role']} record")
        got[r["role"]] = r

    out, failures, unmeasurable, mismatches = [], [], [], []
    for key in sorted(trials, key=lambda k: min(r["seq"] for r in trials[k].values())):
        got = trials[key]
        label = f"repetition {key[0]}" + (f" {key[1]}" if key[1] else "")
        if set(got) != set(roles):
            failures.append(f"{label}: the records do not hold {', '.join(roles)}")
            continue
        t = evaluate_trial(got, requests_dir, hyp, child_a, child_b)
        out.append(t)
        unmeasurable += [f"{label} {x}" for x in t["unmeasurable"]]
        failures += [f"{label}: {x} is false" for x in t["failures"]]
        if t["match"] is False and not t["failures"]:
            mismatches.append(f"{label}: predicted {t['resend']['predicted_reuse']}, reused {t['resend']['cache_n']}")
    counted = [t for t in out if t["match"] is not None and not t["failures"]]
    outcome = ("NOT MEASURABLE" if unmeasurable else "FAILED CONTROL" if failures
               else "MISMATCH" if mismatches else "ALL MATCH")
    return {"run_id": ids["run_id"].pop(), "family": family, "hypothesis": hid, "mode": hyp.mode,
            "models_max": hyp.models_max, "slots": hyp.slots, "child_b": child_b, "trials": out,
            "counts": {"trials": len(out), "counted": len(counted), "matching": sum(t["match"] for t in counted)},
            "unmeasurable": unmeasurable, "failures": failures, "mismatches": mismatches, "outcome": outcome}


def render(report: dict) -> str:
    k = report["counts"]
    show = lambda v: "NOT MEASURABLE" if v is None else str(v)
    server = (f"router --models-max {report['models_max']}" if report["mode"] == "router"
              else "--parallel 1 --slot-save-path")
    lines = [f"m6 {report['run_id']} ({report['family']}, {report['hypothesis']}, {server}, child B {report['child_b']}): "
             f"{report['outcome']}", f"trials: {k['trials']}; counted: {k['counted']}; matching: {k['matching']}", ""]
    if report["mode"] == "router":
        lines += ["| rep | anchor n | anchor reused | B reused | loaded before the resend | predicted | resend reused | result |",
                  "|---|---|---|---|---|---|---|---|"]
    else:
        lines += ["| rep | part | anchor n | anchor reused | generations | predicted | resend reused | result |",
                  "|---|---|---|---|---|---|---|---|"]
    for t in report["trials"]:
        a, s = t["anchor"], t["resend"]
        result = ("not evaluated" if t["match"] is None else "FAILED CONTROL: " + ", ".join(t["failures"]) if t["failures"]
                  else "match" if t["match"] else "MISMATCH")
        if report["mode"] == "router":
            lines.append(f"| {t['repetition']} | {a['n']} | {show(a['cache_n'])} | {show(t['other']['cache_n'])} | "
                         f"{', '.join(s['loaded_before'] or [])} | {s['predicted_reuse']} | {show(s['cache_n'])} | {result} |")
        else:
            gens = f"{(a['process'] or {}).get('generation')} -> {(s['process'] or {}).get('generation')}"
            lines.append(f"| {t['repetition']} | {t['part']} | {a['n']} | {show(a['cache_n'])} | {gens} | "
                         f"{s['predicted_reuse']} | {show(s['cache_n'])} | {result} |")
    for x in report["unmeasurable"] + report["failures"] + report["mismatches"]:
        lines.append(f"- {x}")
    return "\n".join(lines) + "\n"


def summarize(run_id: str, repo_root: Path = REPO_ROOT) -> tuple[dict, str]:
    cfg = load_m6_config(repo_root / "config" / "m6.toml", repo_root)
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
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.summarize_m6")
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
