"""The per-run nonce is the one exception to seeded randomness and must stay the only one."""
import re
from pathlib import Path

import pytest

from prefix_mortality import REPO_ROOT
from prefix_mortality.nonce import new_nonce

_OS_RANDOMNESS = re.compile(
    r"^\s*(import|from)\s+secrets\b|^\s*(import|from)\s+uuid\b|\burandom\(|\bSystemRandom\(|\bgetrandbits\(",
    re.MULTILINE)


def find_os_randomness_offenders(src_dir: Path) -> list[str]:
    return sorted(p.name for p in src_dir.rglob("*.py")
                  if p.name != "nonce.py" and _OS_RANDOMNESS.search(p.read_text(encoding="utf-8")))


def test_nonce_is_hex_of_the_configured_length_and_never_repeats():
    a, b = new_nonce(16), new_nonce(16)
    assert re.fullmatch(r"[0-9a-f]{32}", a) and re.fullmatch(r"[0-9a-f]{32}", b)
    assert a != b
    assert len(new_nonce(4)) == 8


def test_nonce_refuses_a_length_that_is_not_a_positive_int():
    for bad in (True, "16", 16.0):
        with pytest.raises(TypeError):
            new_nonce(bad)
    for bad in (0, -1):
        with pytest.raises(ValueError):
            new_nonce(bad)


def test_only_the_nonce_module_touches_the_os_source():
    assert find_os_randomness_offenders(REPO_ROOT / "src" / "prefix_mortality") == []


def test_os_randomness_check_catches_a_planted_use(tmp_path):
    (tmp_path / "nonce.py").write_text("import secrets\n", encoding="utf-8")
    (tmp_path / "quiet.py").write_text("import os\n\ndef salt():\n    return os.urandom(8)\n", encoding="utf-8")
    (tmp_path / "loud.py").write_text("from uuid import uuid4\n", encoding="utf-8")
    (tmp_path / "clean.py").write_text("import os\n", encoding="utf-8")
    assert find_os_randomness_offenders(tmp_path) == ["loud.py", "quiet.py"]
