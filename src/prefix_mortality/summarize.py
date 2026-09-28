"""Recompute the controls' verdict from what is on disk, and refuse on any disagreement.

Nothing here talks to an engine. Every figure is derived again from the records and from the stored
requests they name: the prompt length from the stored tokens, the header bound from the stored token
pieces and the record's nonce. The result must equal the report the driver wrote, key by key.

The rules, for a llama.cpp server at the pinned commit (its source, not an assumption):
  * reuse is the longest common token prefix with what the server already holds;
  * when the whole prompt is already held, the server still processes the last token.

So, per repetition, with n the prompt's tokens and h the tokens that start before the end of the
run's nonce (nothing after the nonce can be shared with a request that carries a different one):

  write     a first request            reuses at most h
  read      the same bytes again       reuses exactly n - 1
  scramble  fresh random system text   reuses at most h, at a length within the registered tolerance

and in all three the server's two counts must add up to n and its two reuse fields must agree. A
field the server did not report makes the run NOT MEASURABLE. It is never read as zero.
"""
import argparse
import json
import sys
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import load_controls_config
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.record import load_request, read

CONTROLS = ("write", "read", "scramble")
FIELDS = ("cache_n", "prompt_n", "usage_cached_tokens")


def header_tokens(tokens: list[dict], nonce: str) -> int:
    """How many tokens start before the end of the nonce."""
    text = "".join(t["piece"] for t in tokens)
    at = text.find(nonce)
    if at < 0:
        raise ValueError("the nonce is not in the rendered prompt; the request was not isolated")
    end, offset, count = at + len(nonce), 0, 0
    for t in tokens:
        if offset >= end:
            break
        count += 1
        offset += len(t["piece"])
    return count


def derive(record: dict, requests_dir: Path) -> dict:
    stored = load_request(requests_dir, record["request_sha256"])
    o = record["observed"]
    return {"request_sha256": record["request_sha256"], "n": len(stored["tokens"]),
            "h": header_tokens(stored["tokens"], record["nonce"]), **{f: o.get(f) for f in FIELDS}}


def _checks(control: str, d: dict, write: dict | None, tolerance: int) -> dict:
    c = {"counts_add_up": d["cache_n"] + d["prompt_n"] == d["n"],
         "fields_agree": d["usage_cached_tokens"] == d["cache_n"]}
    if control == "read":
        c["same_bytes_as_write"] = d["request_sha256"] == write["request_sha256"]
        c["reuses_all_but_one"] = d["cache_n"] == d["n"] - 1
    else:
        c["reuses_at_most_header"] = d["cache_n"] <= d["h"]
    if control == "scramble":
        c["length_within_tolerance"] = abs(d["n"] - write["n"]) <= tolerance
    return c


def evaluate(records: list[dict], requests_dir: Path, tolerance: int) -> dict:
    if not records:
        raise ValueError("no record to evaluate")
    run_ids, families = {r["run_id"] for r in records}, {r["family"] for r in records}
    if len(run_ids) != 1 or len(families) != 1:
        raise ValueError(f"records mix runs or families: {sorted(run_ids)} {sorted(families)}")
    reps: dict[int, dict] = {}
    for r in records:
        slot = reps.setdefault(r["repetition"], {})
        if r["control"] not in CONTROLS or r["control"] in slot:
            raise ValueError(f"repetition {r['repetition']}: unexpected or repeated control {r['control']!r}")
        slot[r["control"]] = derive(r, requests_dir)

    failures, unmeasurable, out = [], [], []
    for rep in sorted(reps):
        got = reps[rep]
        row = {"repetition": rep}
        for control in CONTROLS:
            if control not in got:
                failures.append(f"repetition {rep}: no {control} record")
                continue
            d = got[control]
            missing = [f for f in FIELDS if d[f] is None]
            if missing:
                unmeasurable.append(f"repetition {rep} {control}: the server reported no {', '.join(missing)}")
                row[control] = {**d, "checks": None}
                continue
            if control != "write" and ("write" not in got or any(got["write"][f] is None for f in FIELDS)):
                row[control] = {**d, "checks": None}
                continue
            checks = _checks(control, d, got.get("write"), tolerance)
            row[control] = {**d, "checks": checks}
            failures += [f"repetition {rep} {control}: {k} is false" for k, ok in checks.items() if not ok]
        out.append(row)

    verdict = "NOT MEASURABLE" if unmeasurable else ("FAIL" if failures else "PASS")
    return {"run_id": run_ids.pop(), "family": families.pop(), "tolerance_tokens": tolerance,
            "repetitions": out, "unmeasurable": unmeasurable, "failures": failures, "verdict": verdict}


def render(report: dict) -> str:
    lines = [f"controls {report['run_id']} ({report['family']}): {report['verdict']}", "",
             "| rep | control | prompt tokens | header bound | reused | processed | checks |",
             "|---|---|---|---|---|---|---|"]
    for row in report["repetitions"]:
        for control in CONTROLS:
            d = row.get(control)
            if d is None:
                continue
            show = lambda v: "NOT MEASURABLE" if v is None else str(v)
            checks = "not evaluated" if d["checks"] is None else (
                "ok" if all(d["checks"].values()) else "FAILED: " + ", ".join(k for k, v in d["checks"].items() if not v))
            lines.append(f"| {row['repetition']} | {control} | {d['n']} | {d['h']} | {show(d['cache_n'])} | "
                         f"{show(d['prompt_n'])} | {checks} |")
    for x in report["unmeasurable"] + report["failures"]:
        lines.append(f"- {x}")
    return "\n".join(lines) + "\n"


def summarize(run_id: str, repo_root: Path = REPO_ROOT) -> tuple[dict, str]:
    cfg = load_controls_config(repo_root / "config" / "controls.toml", repo_root)
    records = read(cfg.corpus_dir / f"{run_id}.jsonl")
    current = {"controls": sha256_text_file(repo_root / "config" / "controls.toml"),
               "engines": sha256_text_file(repo_root / "config" / "engines.toml")}
    for r in records:
        if r.get("config_sha256") != current:
            raise ValueError(f"record {r.get('seq')} was written under a different config than the one on disk")
    rp = cfg.results_dir / run_id / "report.json"
    if not rp.exists():
        raise ValueError(f"{rp} does not exist; the driver wrote no report for this run")
    recorded = json.loads(rp.read_text(encoding="utf-8"))
    report = evaluate(records, repo_root / "corpus" / "requests", cfg.length_tolerance_tokens)
    if report != recorded:
        diff = sorted(k for k in set(report) | set(recorded) if report.get(k) != recorded.get(k))
        raise ValueError(f"the records do not reproduce the driver's report; differing keys: {diff}")
    text = render(report)
    (cfg.results_dir / run_id / "summary.md").write_text(text, encoding="utf-8", newline="\n")
    return report, text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.summarize")
    ap.add_argument("--run", required=True, help="run id, the name of the record file without .jsonl")
    a = ap.parse_args(argv)
    try:
        report, text = summarize(a.run)
    except (ValueError, KeyError) as e:
        print(f"SUMMARY REFUSED: {e}".encode("ascii", "backslashreplace").decode("ascii"))
        return 2
    print(text.encode("ascii", "backslashreplace").decode("ascii"))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
