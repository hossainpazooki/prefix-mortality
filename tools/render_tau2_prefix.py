"""Render the tau2-bench airline base prefix: the system prompt and the tool schemas an agent request
carries and a result file's message list does not (ledger entry 0001).

Run ONCE, by an interpreter that has tau2 installed from a checkout at the pinned commit -- never by
this repo's own environment, and never imported from `src/`:

    <tau2-env>/python tools/render_tau2_prefix.py --tau2-root <checkout> \
        --expect-commit <BASE_PREFIX_SHA> --out corpus/base_prefix/tau2-airline

What it writes is a RECONSTRUCTION at a public commit. The published result files record commits
that are absent from the public history and record no tool schemas, so the bytes their runs sent
cannot be recovered; `provenance.json` says so in the artifact itself.

Refuses (exit 2, nothing written) when: the checkout is not at the expected commit; the paths the
rendering reads are dirty; the imported `tau2` is not the checkout's; the policy tau2 loaded is not
the checkout's policy file; any output already exists.
"""
import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

READ_PATHS = ("src/tau2/agent/llm_agent.py", "src/tau2/environment", "src/tau2/domains/airline",
              "data/tau2/domains/airline/policy.md", "data/tau2/domains/airline/db.json")
PACKAGES = ("tau2", "pydantic", "pydantic_core", "docstring_parser", "litellm", "websockets")
OUTPUTS = ("system.txt", "tools.json")


class Refusal(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if r.returncode != 0:
        raise Refusal(f"git {' '.join(args)} failed in {root}: {r.stderr.strip()[:200]}")
    return r.stdout


def _versions() -> dict:
    out = {}
    for p in PACKAGES:
        try:
            out[p] = version(p)
        except PackageNotFoundError:
            out[p] = None          # not installed: recorded as absent, never as a version
    return out


def render(tau2_root: Path, expect_commit: str, out_dir: Path) -> dict:
    tau2_root, out_dir = Path(tau2_root).resolve(), Path(out_dir)
    head = _git(tau2_root, "rev-parse", "HEAD").strip()
    if head != expect_commit:
        raise Refusal(f"checkout is at {head}, expected {expect_commit}")
    dirty = _git(tau2_root, "status", "--porcelain", "--", *READ_PATHS).strip()
    if dirty:
        raise Refusal(f"the paths the rendering reads are dirty in {tau2_root}:\n{dirty}")
    existing = [n for n in (*OUTPUTS, "provenance.json") if (out_dir / n).exists()]
    if existing:
        raise Refusal(f"{out_dir} already holds {existing}; a fixture is rendered once -- a re-render goes "
                      "to a fresh directory and enters by a ledger entry")

    import tau2
    from tau2.agent.llm_agent import LLMAgent
    from tau2.domains.airline.environment import get_environment

    src = Path(tau2.__file__).resolve()
    if tau2_root not in src.parents:
        raise Refusal(f"the imported tau2 is {src}, which is not under {tau2_root}")

    env = get_environment()
    tools = env.get_tools()
    policy = env.get_policy()
    policy_file = _lf((tau2_root / "data/tau2/domains/airline/policy.md").read_bytes().decode("utf-8"))
    if _lf(policy) != policy_file:
        raise Refusal("the policy tau2 loaded is not the checkout's data/tau2/domains/airline/policy.md")

    agent = LLMAgent(tools=tools, domain_policy=policy, llm="never-called")
    system = _lf(agent.system_prompt)
    schemas = [t.openai_schema for t in tools]
    names = [s["function"]["name"] for s in schemas]
    if len(set(names)) != len(names) or not names:
        raise Refusal(f"tool names are empty or not unique: {names}")

    # Key order and tool order are kept exactly as tau2 produced them: order is part of what a
    # serialization experiment perturbs, so the fixture must not normalize it away.
    payload = {
        "system.txt": system.encode("utf-8"),
        "tools.json": (json.dumps(schemas, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
    }
    script = Path(__file__).resolve()
    provenance = {
        "what": "tau2-bench airline base prefix: system prompt and tool schemas",
        "evidence": "reconstructed",
        "statement": "Rendered by tau2's own code at a public commit. The published result files record "
                     "commits absent from the public history and no tool schemas; the bytes their runs "
                     "sent are not recoverable.",
        "source_repo": "https://github.com/sierra-research/tau2-bench",
        "source_commit": head,
        "source_paths_read": list(READ_PATHS),
        "script": "tools/render_tau2_prefix.py",
        "script_sha256_lf": _sha256(_lf(script.read_bytes().decode("utf-8")).encode("utf-8")),
        "rendered_utc_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "python": platform.python_version(),
        "platform": platform.system(),
        "packages": _versions(),
        "agent_class": "tau2.agent.llm_agent.LLMAgent",
        "policy_sha256": _sha256(policy_file.encode("utf-8")),
        "policy_bytes": len(policy_file.encode("utf-8")),
        "tool_count": len(names),
        "tool_names": names,
        "outputs": {n: {"sha256": _sha256(b), "bytes": len(b)} for n, b in payload.items()},
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    for n, b in payload.items():
        (out_dir / n).write_bytes(b)
    (out_dir / "provenance.json").write_bytes(
        (json.dumps(provenance, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("utf-8"))
    return provenance


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="render_tau2_prefix")
    ap.add_argument("--tau2-root", required=True)
    ap.add_argument("--expect-commit", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        p = render(Path(a.tau2_root), a.expect_commit, Path(a.out))
    except Refusal as e:
        print(f"RENDER REFUSED: {e}".encode("ascii", "backslashreplace").decode("ascii"), file=sys.stderr)
        return 2
    for n, o in p["outputs"].items():
        print(f"{n} {o['bytes']} bytes sha256 {o['sha256']}")
    print(f"tools {p['tool_count']} policy sha256 {p['policy_sha256']} commit {p['source_commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
