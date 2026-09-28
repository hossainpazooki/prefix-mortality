"""The request log: one JSON object per line, append-only, plus the requests themselves.

`corpus/live/<experiment>/<run_id>.jsonl` holds the records. `corpus/requests/<sha256>.json` holds,
for each distinct request, the body as sent, the prompt as the engine rendered it, and the tokens of
that prompt. The name is the sha256 of the body bytes, so a record points at exactly what was sent.
No header is ever written: a key has no path into this module.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from prefix_mortality.hashing import sha256_hex

SCHEMA_VERSION = 1


def _compact(obj) -> bytes:
    """One line, sorted keys, ASCII: a request file holds thousands of tokens and is read by code."""
    return (json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def body_bytes(body: dict) -> bytes:
    """The bytes that go on the wire. Key order is the caller's; nothing is sorted or re-spaced."""
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def store_request(requests_dir: Path, body: bytes, rendered: str, tokens: list[dict]) -> str:
    """Write the request once under its own hash; a second write of the same hash must be identical."""
    sha = sha256_hex(body)
    data = _compact({"body": body.decode("utf-8"), "rendered": rendered,
                     "token_ids": [t["id"] for t in tokens], "token_pieces": [t["piece"] for t in tokens]})
    p = Path(requests_dir) / f"{sha}.json"
    if p.exists():
        if p.read_bytes() != data:
            raise ValueError(f"{p.name} exists with different content: the same request bytes rendered or "
                             "tokenized differently than before")
        return sha
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return sha


def load_request(requests_dir: Path, sha: str) -> dict:
    p = Path(requests_dir) / f"{sha}.json"
    if not p.exists():
        raise ValueError(f"request {sha} is named by a record and missing from {requests_dir}")
    d = json.loads(p.read_text(encoding="utf-8"))
    if sha256_hex(d["body"].encode("utf-8")) != sha:
        raise ValueError(f"{p.name} does not hash to its own name")
    if len(d["token_ids"]) != len(d["token_pieces"]):
        raise ValueError(f"{p.name} holds {len(d['token_ids'])} token ids and {len(d['token_pieces'])} pieces")
    return {"body": d["body"], "rendered": d["rendered"],
            "tokens": [{"id": i, "piece": p} for i, p in zip(d["token_ids"], d["token_pieces"])]}


def append(path: Path, record: dict) -> None:
    line = json.dumps(record, sort_keys=True, ensure_ascii=True, allow_nan=False)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def read(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        raise ValueError(f"{path} does not exist; nothing was recorded")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
