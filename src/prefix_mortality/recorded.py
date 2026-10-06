"""Recorded agent runs: a subset of tau2-bench's published result file, vendored with its provenance,
and the statistics other experiments cite from it.

`extract` reads one published result file, keeps one trial per task (in file order), drops each
message's `raw_data` (a copy of the message in the provider's shape), and writes `simulations.json`
beside a `provenance.json` that names the source commit, path, bytes and sha256, the selection, the
dropped field and the output's own sha256. It refuses to overwrite. `load` reads a vendored folder
back and refuses when the simulations file does not hash to its provenance. `stats` recomputes, from
the loaded simulations alone, the figures a ledger entry may cite: counts, assistant turns, and the
idle the serving side sees between an assistant message and the next message of the conversation
(the next request leaves when that message exists). Timestamps are tau2's, written by its own
process; nothing here is measured on an engine.

The published files carry no tool schemas and no cache field in `usage`: they are trajectories, not
an instrument (read 2026-10-06).
"""
import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.hashing import sha256_hex

SIMULATIONS = "simulations.json"
PROVENANCE = "provenance.json"
DROPPED = ("raw_data",)
INFO_KEPT = ("git_commit", "num_trials", "max_steps", "max_errors", "seed")


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=True, sort_keys=True, indent=1) + "\n"


def select(source: dict, trial: int) -> list[dict]:
    """One simulation per task: those with `trial == trial`, in file order, `raw_data` dropped."""
    out = []
    for s in source["simulations"]:
        if s.get("trial") != trial:
            continue
        sim = {k: v for k, v in s.items() if k != "messages"}
        sim["messages"] = [{k: v for k, v in m.items() if k not in DROPPED} for m in s["messages"]]
        out.append(sim)
    tasks = [s["task_id"] for s in out]
    if len(set(tasks)) != len(tasks):
        raise ValueError(f"trial {trial} holds a task more than once: the selection is not one per task")
    if not out:
        raise ValueError(f"no simulation has trial == {trial}")
    return out


def extract(source_path: Path, out_dir: Path, *, source_repo: str, source_commit: str, source_rel_path: str,
            trial: int = 0) -> dict:
    source_path, out_dir = Path(source_path), Path(out_dir)
    for name in (SIMULATIONS, PROVENANCE):
        if (out_dir / name).exists():
            raise ValueError(f"{out_dir / name} exists; the extractor never overwrites a vendored file")
    raw = source_path.read_bytes()
    source = json.loads(raw.decode("utf-8"))
    sims = select(source, trial)
    text = _dumps(sims)
    info = source.get("info") or {}
    prov = {
        "source_repo": source_repo,
        "source_commit": source_commit,
        "source_path": source_rel_path,
        "source_bytes": len(raw),
        "source_sha256": sha256_hex(raw),
        "source_simulations": len(source["simulations"]),
        "source_info": {k: info.get(k) for k in INFO_KEPT},
        "agent_llm": (info.get("agent_info") or {}).get("llm"),
        "user_llm": (info.get("user_info") or {}).get("llm"),
        "domain": (info.get("environment_info") or {}).get("domain_name"),
        "tool_defs_in_source": (info.get("environment_info") or {}).get("tool_defs") is not None,
        "selection": f"simulations with trial == {trial}, one per task, in file order",
        "dropped_message_fields": list(DROPPED),
        "simulations": len(sims),
        "tasks": sorted({s["task_id"] for s in sims}, key=lambda t: (len(t), t)),
        "output": {SIMULATIONS: {"bytes": len(text.encode("utf-8")), "sha256": sha256_hex(text.encode("utf-8"))}},
        "extractor": "prefix_mortality.recorded.extract",
        "statement": "A subset of a published tau2-bench result file, bytes unchanged except for the dropped field "
                     "and JSON re-serialization. It records trajectories; its usage fields carry no cache count.",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / SIMULATIONS).write_text(text, encoding="utf-8", newline="\n")
    (out_dir / PROVENANCE).write_text(_dumps(prov), encoding="utf-8", newline="\n")
    return prov


def load(folder: Path) -> tuple[list[dict], dict]:
    folder = Path(folder)
    prov = json.loads((folder / PROVENANCE).read_text(encoding="utf-8"))
    data = (folder / SIMULATIONS).read_bytes()
    want = prov["output"][SIMULATIONS]["sha256"]
    if sha256_hex(data) != want:
        raise ValueError(f"{folder / SIMULATIONS} does not hash to its provenance ({want[:12]}...)")
    sims = json.loads(data.decode("utf-8"))
    if len(sims) != prov["simulations"]:
        raise ValueError(f"{folder}: provenance says {prov['simulations']} simulations, file holds {len(sims)}")
    return sims, prov


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _percentiles(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0}
    ys = sorted(xs)
    q = lambda p: ys[min(len(ys) - 1, int(round(p * (len(ys) - 1))))]
    return {"n": len(ys), "p10": q(0.10), "median": statistics.median(ys), "p90": q(0.90), "max": ys[-1]}


def stats(sims: list[dict]) -> dict:
    """What an entry may cite. `idle_to_next_message_s`: from an assistant message to the next message
    of the same simulation, the span in which the serving side has nothing from this conversation;
    `assistant_cycle_s`: from one assistant message to the next."""
    turns, idle, cycle, chars = [], [], [], []
    for s in sims:
        msgs = s["messages"]
        turns.append(sum(1 for m in msgs if m.get("role") == "assistant"))
        chars.append(sum(len(m.get("content") or "") for m in msgs))
        stamped = [(m.get("role"), _ts(m["timestamp"])) for m in msgs if m.get("timestamp")]
        for (r1, t1), (_, t2) in zip(stamped, stamped[1:]):
            if r1 == "assistant":
                idle.append((t2 - t1).total_seconds())
        asst = [t for r, t in stamped if r == "assistant"]
        cycle += [(b - a).total_seconds() for a, b in zip(asst, asst[1:])]
    return {"simulations": len(sims), "tasks": len({s["task_id"] for s in sims}),
            "termination_reasons": sorted({str(s.get("termination_reason")) for s in sims}),
            "assistant_turns": {"min": min(turns), "median": statistics.median(turns), "max": max(turns), "total": sum(turns)},
            "message_chars": {"median": statistics.median(chars), "max": max(chars)},
            "idle_to_next_message_s": _percentiles(idle), "assistant_cycle_s": _percentiles(cycle)}


def render(st: dict, prov: dict) -> str:
    f = lambda v: f"{v:.1f}" if isinstance(v, float) else str(v)
    lines = [f"recorded runs: {prov['agent_llm']} agent, {prov['user_llm']} user simulator, domain {prov['domain']}, "
             f"tau2-bench {prov['source_commit'][:7]}, {prov['selection']}",
             f"simulations: {st['simulations']}; tasks: {st['tasks']}; termination: {', '.join(st['termination_reasons'])}",
             f"assistant turns per simulation: min {st['assistant_turns']['min']}, median {f(st['assistant_turns']['median'])}, "
             f"max {st['assistant_turns']['max']}; total {st['assistant_turns']['total']}", "",
             "| span, seconds | n | p10 | median | p90 | max |", "|---|---|---|---|---|---|"]
    for key, label in (("idle_to_next_message_s", "assistant message to the next message (server idle)"),
                       ("assistant_cycle_s", "assistant message to the next assistant message")):
        p = st[key]
        lines.append(f"| {label} | {p['n']} | {f(p['p10'])} | {f(p['median'])} | {f(p['p90'])} | {f(p['max'])} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.recorded")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--source", required=True, help="a published tau2-bench result file")
    e.add_argument("--out", required=True, help="folder under corpus/recorded/ to create")
    e.add_argument("--repo", required=True)
    e.add_argument("--commit", required=True)
    e.add_argument("--path", required=True, help="the source file's path inside the repository")
    e.add_argument("--trial", type=int, default=0)
    s = sub.add_parser("stats")
    s.add_argument("--dir", required=True, help="a vendored folder under corpus/recorded/")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "extract":
            prov = extract(Path(a.source), REPO_ROOT / a.out, source_repo=a.repo, source_commit=a.commit,
                           source_rel_path=a.path, trial=a.trial)
            print(f"wrote {a.out}: {prov['simulations']} simulations, {prov['output'][SIMULATIONS]['bytes']} bytes, "
                  f"sha256 {prov['output'][SIMULATIONS]['sha256'][:16]}")
            return 0
        sims, prov = load(REPO_ROOT / a.dir)
        print(render(stats(sims), prov).encode("ascii", "backslashreplace").decode("ascii"))
        return 0
    except (ValueError, KeyError, OSError) as e:
        print(f"RECORDED REFUSED: {e}".encode("ascii", "backslashreplace").decode("ascii"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
