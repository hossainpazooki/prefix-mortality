"""The qwen17 cell: the M1 instrument runs a third family whose model pin lives in config/l17.toml
and whose hypotheses live in config/m1q17.toml, because the committed records seal engines.toml and
m1.toml by hash. Same rules, new ids; the gates refuse while either new file is unregistered."""
import json

import pytest

from prefix_mortality.config import load_l17_config, load_m1q17_config
from prefix_mortality.controls import Refusal
from prefix_mortality.controls import run as controls_run
from prefix_mortality.hashing import sha256_file_bytes, sha256_text_file
from prefix_mortality.llamacpp import Client
from prefix_mortality.m1 import run
from prefix_mortality.record import read
from prefix_mortality.summarize_m1 import summarize
from tests.fake_llamacpp import serve
from tests.test_m1 import SITES, _world

M1Q17_TOML = '''
[m1q17]
repetitions = 2
replacement = "zebra"
system_fractions = [0.0, 0.05, 0.5, 0.9]
tool_indexes = [0, 2]
edit_user_message = true
similarity_threshold = 0.10
threshold_margin = 0.002
corpus_dir = "corpus/live/m1q17"
results_dir = "results/m1q17"
registered_by = "%s"
[m1q17.hypotheses.H-M1L1Q17]
slots = 1
rule = "prefix"
[m1q17.hypotheses.H-M1LDQ17]
slots = 4
rule = "threshold"
'''

L17_TOML = '''
[l17]
registered_by = "%s"
[l17.model]
family = "qwen17"
hf_repo = "example/model-17"
file = "model17.gguf"
sha256 = "%s"
'''


def _world17(tmp_path, *, l17_registered="0028", m1q17_registered="0029"):
    w = _world(tmp_path)
    root = w["root"]
    (root / "corpus" / "live" / "m1q17").mkdir(parents=True)
    model17 = root / "model17.gguf"
    model17.write_bytes(b"other bytes standing in for the 1.7B gguf")
    (root / "config" / "l17.toml").write_text(L17_TOML % (l17_registered, sha256_file_bytes(model17)),
                                              encoding="utf-8")
    (root / "config" / "m1q17.toml").write_text(M1Q17_TOML % m1q17_registered, encoding="utf-8")
    w.update(model17=model17, l17=load_l17_config(root / "config" / "l17.toml"),
             m1q17=load_m1q17_config(root / "config" / "m1q17.toml", root))
    return w


def _run17(tmp_path, hid, *, slots=1, **kw):
    w = _world17(tmp_path, **kw)
    with serve("faithful", slots=slots) as (url, _):
        report = run(w["m1q17"], w["controls"], w["engine"], "qwen17", hid, Client(url, 30.0), w["model17"],
                     repo_root=w["root"], fixture=w["root"] / "fixture", l17=w["l17"])
    return w, report


def test_the_prefix_rule_holds_for_the_qwen17_family_and_the_records_pin_both_new_files(tmp_path):
    w, report = _run17(tmp_path, "H-M1L1Q17")
    assert report["outcome"] == "ALL MATCH"
    assert [t["site"] for t in report["trials"]] == SITES * 2
    records = read(w["m1q17"].corpus_dir / f"{report['run_id']}.jsonl")
    assert all(r["model_file"] == "model17.gguf" and r["model_sha256"] == w["l17"].model.sha256 for r in records)
    assert all(r["experiment"] == "m1q17" for r in records)
    want = {"controls": sha256_text_file(w["controls"].config_path),
            "engines": sha256_text_file(w["engine"].config_path),
            "m1q17": sha256_text_file(w["m1q17"].config_path),
            "l17": sha256_text_file(w["l17"].config_path)}
    assert all(r["config_sha256"] == want for r in records)


def test_the_threshold_rule_holds_for_the_qwen17_family(tmp_path):
    w, report = _run17(tmp_path, "H-M1LDQ17", slots=4)
    assert report["outcome"] == "ALL MATCH"
    below = {t["site"] for t in report["trials"]
             if t["edited"]["first_differing_token"] / t["edited"]["n"] <= 0.10}
    assert below and all(t["edited"]["cache_n"] == 0 for t in report["trials"] if t["site"] in below)


def test_summarize_resolves_the_q17_run_and_reproduces_the_report(tmp_path):
    w, report = _run17(tmp_path, "H-M1L1Q17")
    again, text = summarize(report["run_id"], repo_root=w["root"])
    assert again == report and "H-M1L1Q17" in text


@pytest.mark.parametrize("kw,needle", [
    ({"l17_registered": ""}, "l17.toml is UNREGISTERED"),
    ({"m1q17_registered": ""}, "m1q17.toml is UNREGISTERED"),
])
def test_an_unregistered_new_file_refuses_and_records_nothing(tmp_path, kw, needle):
    w = _world17(tmp_path, **kw)
    with serve("faithful", slots=1) as (url, _):
        with pytest.raises(Refusal, match=needle):
            run(w["m1q17"], w["controls"], w["engine"], "qwen17", "H-M1L1Q17", Client(url, 30.0), w["model17"],
                repo_root=w["root"], fixture=w["root"] / "fixture", l17=w["l17"])
    assert not list(w["m1q17"].corpus_dir.glob("*.jsonl"))


def test_controls_run_for_the_qwen17_family_pins_l17_and_gates_its_registration(tmp_path):
    w = _world17(tmp_path)
    (w["root"] / "corpus" / "live" / "controls").mkdir(parents=True)
    with serve("faithful", slots=1) as (url, _):
        report = controls_run(w["controls"], w["engine"], "qwen17", Client(url, 30.0), w["model17"],
                              repo_root=w["root"], fixture=w["root"] / "fixture", l17=w["l17"])
    assert report["verdict"] == "PASS"
    records = read(w["controls"].corpus_dir / f"{report['run_id']}.jsonl")
    assert all("l17" in r["config_sha256"] and r["model_file"] == "model17.gguf" for r in records)


def test_the_wrong_model_file_for_the_family_is_refused_by_hash(tmp_path):
    w = _world17(tmp_path)
    with serve("faithful", slots=1) as (url, _):
        with pytest.raises(Refusal, match="hashes to"):
            run(w["m1q17"], w["controls"], w["engine"], "qwen17", "H-M1L1Q17", Client(url, 30.0), w["model"],
                repo_root=w["root"], fixture=w["root"] / "fixture", l17=w["l17"])
