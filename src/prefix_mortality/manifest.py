"""The corpus manifest: sha256 and size of every file under `corpus/`, checked against disk in both
directions.

The corpus is part of the record, so it is tracked; a tracked file can still be edited, dropped or
added without anyone saying so. `check` refuses on a file the manifest names and disk lacks, a file disk
holds and the manifest does not name, and a file whose bytes or size differ. Raw bytes are hashed:
`.gitattributes` marks `corpus/**` as `-text`, so a checkout never rewrites a line ending there.

`MANIFEST.json` itself and the `.gitkeep` placeholders are outside the manifest.
"""
import argparse
import json
import sys
from pathlib import Path

from prefix_mortality import REPO_ROOT
from prefix_mortality.hashing import canonical_bytes, sha256_file_bytes

MANIFEST_NAME = "MANIFEST.json"
_SKIP = {MANIFEST_NAME, ".gitkeep"}


def build(corpus_dir: Path) -> dict:
    corpus_dir = Path(corpus_dir)
    if not corpus_dir.is_dir():
        raise ValueError(f"{corpus_dir} does not exist; there is no corpus to list")
    files = {}
    for p in sorted(corpus_dir.rglob("*")):
        if p.is_file() and p.name not in _SKIP:
            files[p.relative_to(corpus_dir).as_posix()] = {"sha256": sha256_file_bytes(p),
                                                           "bytes": p.stat().st_size}
    return {"manifest_version": 1, "files": files}


def write(corpus_dir: Path) -> dict:
    m = build(corpus_dir)
    (Path(corpus_dir) / MANIFEST_NAME).write_bytes(canonical_bytes(m))
    return m


def check(corpus_dir: Path) -> list[str]:
    mp = Path(corpus_dir) / MANIFEST_NAME
    if not mp.exists():
        return [f"{mp} does not exist; the corpus has no manifest to be checked against"]
    recorded = json.loads(mp.read_text(encoding="utf-8")).get("files")
    if not isinstance(recorded, dict):
        return [f"{mp} has no `files` table"]
    disk = build(corpus_dir)["files"]
    problems = [f"{k}: named in the manifest, missing on disk" for k in sorted(set(recorded) - set(disk))]
    problems += [f"{k}: on disk, not named in the manifest" for k in sorted(set(disk) - set(recorded))]
    for k in sorted(set(disk) & set(recorded)):
        if disk[k] != recorded[k]:
            problems.append(f"{k}: disk is {disk[k]['bytes']} bytes sha256 {disk[k]['sha256'][:12]}..., manifest "
                            f"says {recorded[k].get('bytes')} bytes sha256 {str(recorded[k].get('sha256'))[:12]}...")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prefix_mortality.manifest")
    ap.add_argument("cmd", choices=("check", "write"))
    ap.add_argument("--corpus", default=str(REPO_ROOT / "corpus"))
    a = ap.parse_args(argv)
    try:
        if a.cmd == "write":
            print(f"manifest written: {len(write(Path(a.corpus))['files'])} file(s)")
            return 0
        problems = check(Path(a.corpus))
    except ValueError as e:
        problems = [str(e)]
    for p in problems:
        print("MANIFEST:", p.encode("ascii", "backslashreplace").decode("ascii"))
    print("manifest ok" if not problems else f"manifest: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
