"""The corpus manifest agrees with disk in both directions, and says so by file when it does not."""
import json

from prefix_mortality import REPO_ROOT
from prefix_mortality.manifest import MANIFEST_NAME, build, check, main, write


def _corpus(tmp_path):
    c = tmp_path / "corpus"
    (c / "live" / "controls").mkdir(parents=True)
    (c / "requests").mkdir()
    (c / "live" / ".gitkeep").write_bytes(b"")
    (c / "live" / "controls" / "run.jsonl").write_bytes(b'{"seq": 0}\n')
    (c / "requests" / "ab.json").write_bytes(b"{}\n")
    return c


def test_write_then_check_is_clean_and_skips_placeholders(tmp_path):
    c = _corpus(tmp_path)
    m = write(c)
    assert sorted(m["files"]) == ["live/controls/run.jsonl", "requests/ab.json"]
    assert m["files"]["requests/ab.json"]["bytes"] == 3
    assert check(c) == []


def test_check_names_a_changed_a_missing_and_an_added_file(tmp_path):
    c = _corpus(tmp_path)
    write(c)
    (c / "live" / "controls" / "run.jsonl").write_bytes(b'{"seq": 1}\n')      # same size, different bytes
    (c / "requests" / "ab.json").unlink()
    (c / "requests" / "cd.json").write_bytes(b"{}\n")
    problems = check(c)
    assert len(problems) == 3
    assert any(p.startswith("requests/ab.json: named in the manifest, missing on disk") for p in problems)
    assert any(p.startswith("requests/cd.json: on disk, not named in the manifest") for p in problems)
    assert any(p.startswith("live/controls/run.jsonl: disk is 11 bytes") for p in problems)


def test_check_refuses_without_a_manifest_or_a_files_table(tmp_path):
    c = _corpus(tmp_path)
    assert "does not exist" in check(c)[0]
    (c / MANIFEST_NAME).write_text(json.dumps({"manifest_version": 1}), encoding="utf-8")
    assert "no `files` table" in check(c)[0]


def test_cli_exit_codes(tmp_path, capsys):
    c = _corpus(tmp_path)
    assert main(["check", "--corpus", str(c)]) == 1
    assert main(["write", "--corpus", str(c)]) == 0
    assert main(["check", "--corpus", str(c)]) == 0
    assert main(["check", "--corpus", str(tmp_path / "nowhere")]) == 1
    assert "manifest ok" in capsys.readouterr().out


def test_repo_corpus_matches_its_manifest():
    assert check(REPO_ROOT / "corpus") == []
    assert build(REPO_ROOT / "corpus")["files"], "the corpus holds the base-prefix fixture at least"
