"""Lifespan on recorded runs: recompute every request from what is on disk, and refuse on any
disagreement.

Nothing here talks to an engine. A run replays recorded conversations against one server, one request
per assistant turn, with no nonce: C = 1 replays every conversation one after another in file order;
C > 1 replays the C conversations with the most assistant turns in round robin. The predicted reuse of
each request is the pinned server's slot and prompt-cache policy (`slotsim`, read from the source at
the pin) applied to the stored token lists in send order; the one token each response generated is
recorded but never held (the slot stops before it is fed back). The driver writes the prediction
before the request is sent; this module recomputes it from the stored tokens and refuses a record that
carries another value.

A request matches when its reported reuse equals the prediction. A request the policy decides by one
token or less (`near`) is reported and not counted, as M1's threshold margin. Controls: the first
request of a run reuses 0 (a fresh server); every request's two counts add up to its token count and
its two reuse fields agree; the records follow the registered schedule exactly, with no record between
two of them; one local date. NOT MEASURABLE, never zero: a field the server did not report, no slot
context, a request that does not fit it.

What the run measures, per conversation: the share of its tokens served from a held prefix, and its
deaths — requests that reused less than the common prefix with the conversation's own previous
request. The first request of a conversation has no
own previous request; what it reuses from another conversation's held prompt is the shared head.
"""
import argparse
import json
import sys
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import M8Config, M8Hypothesis, load_m8_config
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.record import load_request, read
from prefix_mortality.recorded import SIMULATIONS, load as load_recorded
from prefix_mortality.replay import assistant_turns, longest
from prefix_mortality.slotsim import Prediction, SlotSim, Token, lcp, tokens
from prefix_mortality.summarize import FIELDS

CONFIGS = ("controls", "engines")          # plus the M8 config file the records name (`config`, default m8)
SIM_KEYS = ("slot", "by", "f_sim", "f_keep", "cache_searched", "saved", "restored", "erased", "evicted")


def schedule(sims: list[dict], c: int) -> list[tuple[str, int, int]]:
    """(task id, message index of the assistant turn, 1-based turn number) in send order."""
    if c == 1:
        return [(s["task_id"], t, i + 1) for s in sims for i, t in enumerate(assistant_turns(s))]
    chosen = [(s["task_id"], assistant_turns(s)) for s in longest(sims, c)]
    out = []
    for i in range(max(len(t) for _, t in chosen)):
        for task_id, turns in chosen:
            if i < len(turns):
                out.append((task_id, turns[i], i + 1))
    return out


def make_sim(cfg: M8Config, hyp: M8Hypothesis, family: str) -> SlotSim:
    return SlotSim(slots=hyp.slots, similarity=cfg.similarity_threshold, cache_limit_bytes=cfg.cache_limit_bytes,
                   bytes_per_token=cfg.bytes_per_token(family))


def prediction_fields(p: Prediction) -> dict:
    """What the driver stores before it sends, and what is recomputed here."""
    return {"predicted_reuse": p.reuse, "near": list(p.near), "sim": {k: getattr(p, k) for k in SIM_KEYS}}


def generated_text(response: dict) -> str:
    """The text of the one token the response generated; "" when the server reported none as text
    (a reasoning parser may have consumed it), which matches nothing."""
    try:
        content = response["choices"][0]["message"].get("content")
    except (KeyError, IndexError, TypeError, AttributeError):
        return ""
    return content if isinstance(content, str) else ""


def _toks(stored: dict) -> list[Token]:
    return tokens([t["id"] for t in stored["tokens"]], [t["piece"] for t in stored["tokens"]])


def _ctx(rec: dict):
    v = (rec.get("server") or {}).get("n_ctx")
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else None


def evaluate_request(rec: dict, toks: list[Token], n_ctx) -> dict:
    """One request from its record and stored tokens. `failures` are failed controls; `match` is the
    result, None when the request is not counted."""
    o = rec["observed"]
    n = len(toks)
    row = {"seq": rec["seq"], "conversation": rec["conversation"], "turn_number": rec["turn_number"], "n": n,
           **{f: o.get(f) for f in FIELDS}, "predicted_reuse": rec["predicted_reuse"],
           "near": list(rec.get("near") or []), "sim": dict(rec.get("sim") or {}), "generated": rec.get("generated"),
           "own_previous_lcp": None, "death": None, "failures": [], "unmeasurable": [], "match": None}
    missing = [f for f in FIELDS if row[f] is None]
    if missing:
        row["unmeasurable"].append(f"the server reported no {', '.join(missing)}")
    if n_ctx is None:
        row["unmeasurable"].append("the server reported no slot context (n_ctx)")
    elif n >= n_ctx:
        row["unmeasurable"].append(f"a request of {n} tokens does not fit the slot context of {n_ctx} tokens")
    if row["unmeasurable"]:
        return row
    checks = {"counts_add_up": row["cache_n"] + row["prompt_n"] == n,
              "fields_agree": row["usage_cached_tokens"] == row["cache_n"]}
    row["failures"] = [k for k, ok in checks.items() if not ok]
    if not row["near"]:
        row["match"] = row["cache_n"] == row["predicted_reuse"]
    return row


def evaluate(records: list[dict], requests_dir: Path, cfg: M8Config) -> dict:
    if not records:
        raise ValueError("no record to evaluate")
    ids = {key: {r.get(key) for r in records} for key in ("run_id", "family", "hypothesis", "c", "recorded_sha256")}
    if any(len(v) != 1 for v in ids.values()):
        mixed = {key: sorted(map(str, v)) for key, v in ids.items()}
        raise ValueError(f"records mix runs, families, hypotheses, C or corpora: {mixed}")
    hid, family, c = ids["hypothesis"].pop(), ids["family"].pop(), ids["c"].pop()
    hyp = cfg.hypothesis(hid)
    if c not in hyp.interleave:
        raise ValueError(f"{hid} registers C in {list(hyp.interleave)}; the records say {c!r}")
    slots = {(r.get("server") or {}).get("total_slots") for r in records}
    if slots != {hyp.slots}:
        raise ValueError(f"{hid} requires a server reporting {hyp.slots} slot(s); the records say "
                         f"{sorted(map(str, slots))}. This run is not that experiment")
    ctxs = {_ctx(r) for r in records} - {None}
    if len(ctxs) > 1:
        raise ValueError(f"records mix slot contexts {sorted(ctxs)}; this run is not one experiment")
    n_ctx = ctxs.pop() if ctxs else None
    sims, prov = load_recorded(cfg.recorded_dir)
    if ids["recorded_sha256"].pop() != prov["output"][SIMULATIONS]["sha256"]:
        raise ValueError("the records name a recorded corpus other than the one on disk")
    plan = schedule(sims, c)
    records = sorted(records, key=lambda r: r["seq"])
    if [r["seq"] for r in records] != list(range(1, len(records) + 1)):
        raise ValueError("record sequence numbers are not dense from 1; a record is missing or repeated")
    if len(records) > len(plan):
        raise ValueError(f"{len(records)} records for a schedule of {len(plan)} requests")
    for r, (task_id, turn_index, turn_number) in zip(records, plan):
        if (r.get("conversation"), r.get("turn_index"), r.get("turn_number")) != (task_id, turn_index, turn_number):
            raise ValueError(f"record {r['seq']} is not the registered schedule's request at that position "
                             f"({task_id!r} turn {turn_number}); the records do not follow the schedule")

    sim = make_sim(cfg, hyp, family)
    rows, previous = [], {}
    failures, unmeasurable, mismatches = [], [], []
    for r in records:
        toks = _toks(load_request(requests_dir, r["request_sha256"]))
        want = prediction_fields(sim.predict(toks))
        got = {"predicted_reuse": r.get("predicted_reuse"), "near": list(r.get("near") or []), "sim": r.get("sim")}
        if got != want:
            raise ValueError(f"record {r['seq']} carries a prediction other than the recomputation from the stored "
                             f"tokens: {got} vs {want}")
        row = evaluate_request(r, toks, n_ctx)
        if r["conversation"] in previous:
            row["own_previous_lcp"] = lcp(previous[r["conversation"]], toks)
            if row["cache_n"] is not None:
                row["death"] = row["cache_n"] < row["own_previous_lcp"]
        previous[r["conversation"]] = toks
        sim.commit(toks)
        label = f"request {r['seq']} ({r['conversation']} turn {r['turn_number']})"
        if r["seq"] == 1 and row["cache_n"] is not None and row["cache_n"] != 0:
            row["failures"].append("fresh_server_reuses_0")
        unmeasurable += [f"{label}: {x}" for x in row["unmeasurable"]]
        failures += [f"{label}: {x} is false" for x in row["failures"]]
        if row["match"] is False and not row["failures"]:
            mismatches.append(f"{label}: predicted {row['predicted_reuse']}, reused {row['cache_n']}")
        rows.append(row)
    if len({r.get("local_date") for r in records}) != 1:
        unmeasurable.append("the local date changed during the run (a chat template may carry the date)")

    counted = [x for x in rows if x["match"] is not None and not x["failures"]]
    by_conv: dict[str, dict] = {}
    for x in rows:
        agg = by_conv.setdefault(x["conversation"], {"conversation": x["conversation"], "requests": 0, "tokens": 0,
                                                     "reused": 0, "deaths": 0, "near": 0, "first_request_reuse": None})
        agg["requests"] += 1
        if x["cache_n"] is not None:
            agg["tokens"] += x["n"]
            agg["reused"] += x["cache_n"]
            if agg["first_request_reuse"] is None and x["own_previous_lcp"] is None:
                agg["first_request_reuse"] = x["cache_n"]
        agg["deaths"] += bool(x["death"])
        agg["near"] += bool(x["near"])
    conversations = []
    turns = {s["task_id"]: len(assistant_turns(s)) for s in sims}
    for agg in by_conv.values():
        agg["turns"] = turns[agg["conversation"]]
        agg["share"] = round(agg["reused"] / agg["tokens"], 4) if agg["tokens"] else None
        conversations.append(agg)
    deaths = [{"seq": x["seq"], "conversation": x["conversation"], "turn_number": x["turn_number"],
               "own_previous_lcp": x["own_previous_lcp"], "reused": x["cache_n"], "n": x["n"],
               "predicted": x["predicted_reuse"]} for x in rows if x["death"]]
    outcome = ("NOT MEASURABLE" if unmeasurable else "FAILED CONTROL" if failures
               else "MISMATCH" if mismatches else "ALL MATCH")
    return {"run_id": ids["run_id"].pop(), "family": family, "hypothesis": hid, "c": c, "slots": hyp.slots,
            "schedule_length": len(plan), "requests": rows, "conversations": conversations, "deaths": deaths,
            "counts": {"requests": len(rows), "counted": len(counted), "matching": sum(x["match"] for x in counted),
                       "near": sum(bool(x["near"]) for x in rows), "deaths": len(deaths),
                       "cache_searched": sum(bool((x["sim"] or {}).get("cache_searched")) for x in rows),
                       "restored": sum(bool((x["sim"] or {}).get("restored")) for x in rows),
                       "evicted": sum(int((x["sim"] or {}).get("evicted") or 0) for x in rows)},
            "unmeasurable": unmeasurable, "failures": failures, "mismatches": mismatches, "outcome": outcome}


def render(report: dict) -> str:
    k = report["counts"]
    show = lambda v: "NOT MEASURABLE" if v is None else str(v)
    lines = [f"m8 {report['run_id']} ({report['family']}, {report['hypothesis']}, {report['slots']} slot(s), "
             f"C = {report['c']}): {report['outcome']}",
             f"requests: {k['requests']} of {report['schedule_length']} scheduled; counted: {k['counted']}; "
             f"matching: {k['matching']}; near: {k['near']}; deaths: {k['deaths']}; cache searched: "
             f"{k['cache_searched']}; restored: {k['restored']}; evicted: {k['evicted']}", "",
             "| conversation | turns | requests | tokens | reused | share | first request reuse | deaths | near |",
             "|---|---|---|---|---|---|---|---|---|"]
    for a in report["conversations"]:
        lines.append(f"| {a['conversation']} | {a['turns']} | {a['requests']} | {a['tokens']} | {a['reused']} | "
                     f"{show(a['share'])} | {show(a['first_request_reuse'])} | {a['deaths']} | {a['near']} |")
    if report["deaths"]:
        lines += ["", "| seq | conversation | turn | own previous lcp | predicted | reused | n |", "|---|---|---|---|---|---|---|"]
        for d in report["deaths"]:
            lines.append(f"| {d['seq']} | {d['conversation']} | {d['turn_number']} | {d['own_previous_lcp']} | "
                         f"{d['predicted']} | {show(d['reused'])} | {d['n']} |")
    for x in report["unmeasurable"] + report["failures"] + report["mismatches"]:
        lines.append(f"- {x}")
    return "\n".join(lines) + "\n"


def summarize(run_id: str, repo_root: Path = REPO_ROOT, config: str = "m8") -> tuple[dict, str]:
    cfg = load_m8_config(repo_root / "config" / f"{config}.toml", repo_root)
    records = read(cfg.corpus_dir / f"{run_id}.jsonl")
    current = {key: sha256_text_file(repo_root / "config" / f"{key}.toml") for key in (*CONFIGS, config)}
    for r in records:
        if r.get("config", "m8") != config:
            raise ValueError(f"record {r.get('seq')} names config {r.get('config', 'm8')!r}; this summary reads {config!r}")
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
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.summarize_m8")
    ap.add_argument("--run", required=True, help="run id, the name of the record file without .jsonl")
    ap.add_argument("--config", default="m8", help="the M8 config the run was made under: config/<name>.toml")
    a = ap.parse_args(argv)
    try:
        report, text = summarize(a.run, config=a.config)
    except (ValueError, KeyError) as e:
        print(f"SUMMARY REFUSED: {e}".encode("ascii", "backslashreplace").decode("ascii"))
        return 2
    print(text.encode("ascii", "backslashreplace").decode("ascii"))
    return 0 if report["outcome"] == "ALL MATCH" else 1


if __name__ == "__main__":
    sys.exit(main())
