"""Recompute the V controls' verdict from what is on disk, and refuse on any disagreement.

Nothing here talks to an engine. Every figure is derived again from the records and the stored
requests they name. The result must equal the report the driver wrote, key by key.

The rules, for a vLLM server at the pinned commit (its source, confirmed against the live server):
the prefix cache stores full blocks of B tokens; a hit is the longest stored block chain prefixing
the prompt, capped at the prompt length minus one; `created_cache_tokens` is finalized at the FIRST
output emission, when only the prompt's full blocks carry a hash (the first sampled token is not yet
computed), so it counts the prompt's full blocks that were not a hit and never a generated token:

  hit(n)     = the largest multiple of B at most min(stored chain, n - 1)
  created(n) = max(0, floor(n / B) * B - hit)

(An earlier reading made created include the generated tokens, floor((n + g)/B) * B clipped to n. It
was refuted on the live server at the pin on 2026-10-09: at n = 4867, block 128, with 128 generated
tokens forced via min_tokens, the server reported created 4864 = floor(n/B)*B where that reading
predicted 4867. PrefillStats.finalize runs on the first emitted output, before any decode block.)

So, per repetition, with n the prompt's tokens as the server tokenizes it, run under one block size B
on a server started fresh for the run:

  write     a first request under a fresh nonce   cached = 0; created = floor(n/B)*B
  read      the same bytes again                  cached = floor((n-1)/B)*B; created = floor(n/B)*B - cached
  scramble  fresh random system text, own n'      cached = 0; created = floor(n'/B)*B; n' within tolerance

The zeros are exact, not bounds, because a block matches only whole: they hold only while the tokens
shared across different nonces (the template header) are fewer than B, which is checked per
repetition as lcp(write, scramble) < B from the stored token ids. In all three the reported prompt
size must equal the stored token count. A field the server did not report makes the run NOT
MEASURABLE. It is never read as zero.
"""
import argparse
import json
import sys
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.config import load_controls_config, load_vllm_config
from prefix_mortality.hashing import sha256_text_file
from prefix_mortality.record import load_request, read

CONTROLS = ("write", "read", "scramble")
FIELDS = ("usage_prompt_tokens", "usage_cached_tokens", "usage_created_cache_tokens")


def prediction(control: str, n: int, block: int) -> dict:
    cached = ((n - 1) // block) * block if control == "read" else 0
    return {"cached": cached, "created": max(0, (n // block) * block - cached)}


def _lcp(a: list[int], b: list[int]) -> int:
    k = 0
    while k < min(len(a), len(b)) and a[k] == b[k]:
        k += 1
    return k


def derive(record: dict, requests_dir: Path) -> dict:
    stored = load_request(requests_dir, record["request_sha256"])
    o = record["observed"]
    return {"request_sha256": record["request_sha256"], "n": len(stored["tokens"]),
            "ids": [t["id"] for t in stored["tokens"]], **{f: o.get(f) for f in FIELDS}}


def _checks(control: str, d: dict, write: dict | None, block: int, tolerance: int) -> dict:
    p = prediction(control, d["n"], block)
    c = {"size_agrees": d["usage_prompt_tokens"] == d["n"],
         "cached_as_predicted": d["usage_cached_tokens"] == p["cached"],
         "created_as_predicted": d["usage_created_cache_tokens"] == p["created"]}
    if control == "read":
        c["same_bytes_as_write"] = d["request_sha256"] == write["request_sha256"]
    if control == "scramble":
        c["length_within_tolerance"] = abs(d["n"] - write["n"]) <= tolerance
        c["nonce_isolates_first_block"] = _lcp(d["ids"], write["ids"]) < block
    return c


def evaluate(records: list[dict], requests_dir: Path, block_sizes: tuple[int, ...],
             tolerance: int) -> dict:
    if not records:
        raise ValueError("no record to evaluate")
    for key in ("run_id", "family", "block_size"):
        if len({r.get(key) for r in records}) != 1:
            raise ValueError(f"records mix values of {key}: {sorted({str(r.get(key)) for r in records})}")
    block = records[0]["block_size"]
    if block not in block_sizes:
        raise ValueError(f"block size {block!r} is not registered; registered: {list(block_sizes)}")
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
            keep = {k: v for k, v in d.items() if k != "ids"}
            if missing:
                unmeasurable.append(f"repetition {rep} {control}: the server reported no {', '.join(missing)}")
                row[control] = {**keep, "checks": None}
                continue
            if control != "write" and ("write" not in got or any(got["write"][f] is None for f in FIELDS)):
                row[control] = {**keep, "checks": None}
                continue
            checks = _checks(control, d, got.get("write"), block, tolerance)
            row[control] = {**keep, "checks": checks}
            failures += [f"repetition {rep} {control}: {k} is false" for k, ok in checks.items() if not ok]
        out.append(row)

    verdict = "NOT MEASURABLE" if unmeasurable else ("FAIL" if failures else "PASS")
    return {"run_id": records[0]["run_id"], "family": records[0]["family"], "block_size": block,
            "tolerance_tokens": tolerance, "repetitions": out,
            "unmeasurable": unmeasurable, "failures": failures, "verdict": verdict}


def render(report: dict) -> str:
    lines = [f"vcontrols {report['run_id']} ({report['family']}, block {report['block_size']}): "
             f"{report['verdict']}", "",
             "| rep | control | prompt tokens | cached | created | checks |",
             "|---|---|---|---|---|---|"]
    for row in report["repetitions"]:
        for control in CONTROLS:
            d = row.get(control)
            if d is None:
                continue
            show = lambda v: "NOT MEASURABLE" if v is None else str(v)
            checks = "not evaluated" if d["checks"] is None else (
                "ok" if all(d["checks"].values()) else "FAILED: " + ", ".join(k for k, v in d["checks"].items() if not v))
            lines.append(f"| {row['repetition']} | {control} | {d['n']} | {show(d['usage_cached_tokens'])} | "
                         f"{show(d['usage_created_cache_tokens'])} | {checks} |")
    for x in report["unmeasurable"] + report["failures"]:
        lines.append(f"- {x}")
    return "\n".join(lines) + "\n"


def summarize(run_id: str, repo_root: Path = REPO_ROOT) -> tuple[dict, str]:
    controls = load_controls_config(repo_root / "config" / "controls.toml", repo_root)
    cfg = load_vllm_config(repo_root / "config" / "vllm.toml", repo_root)
    records = read(cfg.corpus_dir / f"{run_id}.jsonl")
    current = {"controls": sha256_text_file(repo_root / "config" / "controls.toml"),
               "vllm": sha256_text_file(repo_root / "config" / "vllm.toml")}
    for r in records:
        if r.get("config_sha256") != current:
            raise ValueError(f"record {r.get('seq')} was written under a different config than the one on disk")
    rp = cfg.results_dir / run_id / "report.json"
    if not rp.exists():
        raise ValueError(f"{rp} does not exist; the driver wrote no report for this run")
    recorded = json.loads(rp.read_text(encoding="utf-8"))
    report = evaluate(records, repo_root / "corpus" / "requests", cfg.block_sizes,
                      controls.length_tolerance_tokens)
    if report != recorded:
        diff = sorted(k for k in set(report) | set(recorded) if report.get(k) != recorded.get(k))
        raise ValueError(f"the records do not reproduce the driver's report; differing keys: {diff}")
    text = render(report)
    (cfg.results_dir / run_id / "summary.md").write_text(text, encoding="utf-8", newline="\n")
    return report, text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.summarize_vcontrols")
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
