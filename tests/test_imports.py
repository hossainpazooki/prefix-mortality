"""Adapted from lag-ladder tests/test_imports.py: this repo's pins, its forbidden imports, and what
git may and may not track."""
import re
import subprocess

import pytest

import prefix_mortality

PINS = {prefix_mortality.CHASSIS_SHA, prefix_mortality.BASE_PREFIX_SHA, prefix_mortality.ENGINE_OBSERVED_SHA}


def test_repo_root_is_the_repo():
    assert (prefix_mortality.REPO_ROOT / "pyproject.toml").exists()


def test_every_pin_in_upstream_md_is_declared_and_vice_versa():
    text = (prefix_mortality.REPO_ROOT / "UPSTREAM.md").read_text(encoding="utf-8")
    shas = set(re.findall(r"\b[0-9a-f]{40}\b", text))
    assert len(PINS) == 3
    assert shas == PINS, shas ^ PINS


def test_engine_config_cites_the_observed_commit():
    text = (prefix_mortality.REPO_ROOT / "config" / "engines.toml").read_text(encoding="utf-8")
    assert prefix_mortality.ENGINE_OBSERVED_SHA in text


# The chassis is copied, never shared; the base prefix is rendered by tau2's own code in a separate
# environment, never imported here.
_FORBIDDEN = ("linear_ceiling", "lag_ladder", "kvt", "tau2")


def _forbidden_imports(text: str) -> list[str]:
    return [m for m in _FORBIDDEN if re.search(rf"^\s*(from|import)\s+{m}\b", text, re.M)]


def test_no_source_file_imports_a_sibling_repo_or_the_base_prefix_source():
    for p in (prefix_mortality.REPO_ROOT / "src").rglob("*.py"):
        assert _forbidden_imports(p.read_text(encoding="utf-8")) == [], p.name


def test_forbidden_import_check_catches_a_planted_import():
    assert _forbidden_imports("import os\nfrom linear_ceiling.e7_stats import summary\n") == ["linear_ceiling"]
    assert _forbidden_imports("    import tau2\n") == ["tau2"]
    assert _forbidden_imports("# from lag_ladder import x is only mentioned here\n") == []


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=prefix_mortality.REPO_ROOT, capture_output=True, text=True)


_ALLOWED_TRACKED_RESULTS_PATHS = {"results/.gitkeep"}


def _tracked_results_paths() -> list[str]:
    proc = _git("ls-files", "--", "results")
    if proc.returncode != 0:
        pytest.fail(f"could not query git for tracked results/ paths: {proc.stderr}")
    return [line for line in proc.stdout.splitlines() if line]


def _assert_no_result_artifacts_tracked(tracked_paths) -> None:
    extras = sorted(set(tracked_paths) - _ALLOWED_TRACKED_RESULTS_PATHS)
    assert not extras, f"unexpected tracked files under results/: {extras}"


def test_results_tree_is_empty_placeholder():
    _assert_no_result_artifacts_tracked(_tracked_results_paths())


def test_results_tree_check_catches_tracked_artifact():
    with pytest.raises(AssertionError):
        _assert_no_result_artifacts_tracked(sorted(_ALLOWED_TRACKED_RESULTS_PATHS | {"results/m1/x/report.json"}))


@pytest.mark.parametrize("path, ignored", [
    (".env", True), (".env.local", True), ("models/qwen.gguf", True), ("results/m1/report.json", True),
    ("corpus/live/controls/run.jsonl", False), ("corpus/requests/ab.json", False),
])
def test_gitignore_hides_keys_and_keeps_the_corpus(path, ignored):
    # exit 0 = ignored, 1 = not ignored; anything else is git failing and must not read as either
    rc = _git("check-ignore", "-q", path).returncode
    assert rc in (0, 1), rc
    assert (rc == 0) is ignored, path
