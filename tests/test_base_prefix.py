"""The base-prefix fixture is what its provenance file and the ledger say it is."""
import hashlib
import json

from prefix_mortality import BASE_PREFIX_REPO, BASE_PREFIX_SHA, REPO_ROOT
from prefix_mortality.hashing import sha256_file_bytes, sha256_text_file

FIXTURE = REPO_ROOT / "corpus" / "base_prefix" / "tau2-airline"


def _provenance() -> dict:
    return json.loads((FIXTURE / "provenance.json").read_text(encoding="utf-8"))


def test_provenance_names_the_pinned_source_and_calls_itself_a_reconstruction():
    p = _provenance()
    assert p["source_repo"] == BASE_PREFIX_REPO and p["source_commit"] == BASE_PREFIX_SHA
    assert p["evidence"] == "reconstructed"
    assert "not recoverable" in p["statement"]


def test_outputs_are_the_bytes_the_provenance_recorded():
    p = _provenance()
    assert sorted(p["outputs"]) == ["system.txt", "tools.json"]
    for name, o in p["outputs"].items():
        f = FIXTURE / name
        assert f.stat().st_size == o["bytes"], name
        assert sha256_file_bytes(f) == o["sha256"], name
        assert b"\r" not in f.read_bytes(), f"{name} carries a carriage return: a checkout rewrote it"


def test_render_script_is_the_one_that_rendered_the_fixture():
    # newline-normalized, so a CRLF checkout of the script does not read as an edit
    assert sha256_text_file(REPO_ROOT / _provenance()["script"]) == _provenance()["script_sha256_lf"]


def test_system_prompt_wraps_exactly_the_recorded_policy():
    p = _provenance()
    s = (FIXTURE / "system.txt").read_bytes().decode("utf-8")
    assert s.startswith("<instructions>\n") and s.endswith("\n</policy>")
    start = s.index("<policy>\n") + len("<policy>\n")
    policy = s[start:s.rindex("\n</policy>")].encode("utf-8")
    assert len(policy) == p["policy_bytes"]
    assert hashlib.sha256(policy).hexdigest() == p["policy_sha256"]


def test_tool_schemas_match_the_recorded_names_in_order():
    p = _provenance()
    tools = json.loads((FIXTURE / "tools.json").read_text(encoding="utf-8"))
    assert all(t["type"] == "function" and set(t["function"]) == {"name", "description", "parameters"} for t in tools)
    names = [t["function"]["name"] for t in tools]
    assert names == p["tool_names"] and len(names) == p["tool_count"] == len(set(names))


def test_environment_listing_carries_the_versions_the_provenance_names():
    env = (FIXTURE / "environment.txt").read_text(encoding="utf-8").splitlines()
    pins = {line.split("==")[0].lower().replace("-", "_"): line.split("==")[1] for line in env if "==" in line}
    for pkg, ver in _provenance()["packages"].items():
        if pkg != "tau2":                      # installed editable from the checkout; named by commit instead
            assert pins.get(pkg) == ver, pkg


def test_ledger_cites_the_fixture_by_the_hashes_on_disk():
    ledger = (REPO_ROOT / "ledger" / "ledger.md").read_text(encoding="utf-8")
    for name, o in _provenance()["outputs"].items():
        assert f"| `{name}` | {o['bytes']:,} | `{o['sha256']}` |" in ledger, name
