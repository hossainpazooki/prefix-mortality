"""A later model family on either lane lives in files of its own (config.FAMILY_FILES), because the
committed records seal engines.toml, vllm.toml, m1.toml and vm1.toml by hash. These tests drive the
general mechanism with a stand-in fourth family: the loaders read a family file by its stem, the
drivers gate on its registration and pin its model, every record hashes the family file under its
stem, the summarizers expect that hash, and an unknown family is refused with the known ones named.
No real model, no real server, no registered id."""
import json

import pytest

from prefix_mortality.config import (FAMILY_FILES, load_l17_config, load_m1sm3_config, load_vfamily_config,
                                     load_vm1_config)
from prefix_mortality.controls import Refusal, _maybe_l17
from prefix_mortality.controls import run as controls_run
from prefix_mortality.hashing import sha256_file_bytes, sha256_text_file
from prefix_mortality.llamacpp import Client as LClient
from prefix_mortality.m1 import run as m1_run
from prefix_mortality.record import read
from prefix_mortality.summarize import summarize as summarize_controls
from prefix_mortality.summarize_m1 import summarize as summarize_m1
from prefix_mortality.summarize_vcontrols import summarize as summarize_vcontrols
from prefix_mortality.summarize_vm1 import summarize as summarize_vm1
from prefix_mortality.vcontrols import _maybe_vfamily
from prefix_mortality.vcontrols import run as vcontrols_run
from prefix_mortality.vllm import Client as VClient
from prefix_mortality.vm1 import run as vm1_run
from tests.fake_llamacpp import serve as lserve
from tests.fake_vllm import serve as vserve
from tests.test_m1 import SITES, _world as _lworld
from tests.test_vcontrols import _world as _vworld
from tests.test_vm1 import VM1

FAMILY = "smollm3"

LSM3_TOML = '''
[lsm3]
registered_by = "{registered}"
[lsm3.model]
family = "smollm3"
hf_repo = "example/SmolLM3-3B-GGUF"
file = "model-sm3.gguf"
sha256 = "{sha}"
{template}'''

TEMPLATE_PIN = '''[lsm3.chat_template]
hf_repo = "example/SmolLM3-3B"
revision = "486a602f"
file = "chat_template.jinja"
sha256 = "{sha}"
'''

M1SM3_TOML = '''
[m1sm3]
repetitions = 2
replacement = "zebra"
system_fractions = [0.0, 0.05, 0.5, 0.9]
tool_indexes = [0, 2]
edit_user_message = true
similarity_threshold = 0.10
threshold_margin = 0.002
corpus_dir = "corpus/live/m1sm3"
results_dir = "results/m1sm3"
registered_by = "{registered}"
[m1sm3.hypotheses.H-M1L1SM3]
slots = 1
rule = "prefix"
[m1sm3.hypotheses.H-M1LDSM3]
slots = 4
rule = "threshold"
'''

VSM3_TOML = '''
[vsm3]
registered_by = "{registered}"
served_model_name = "smollm3-3b"
[vsm3.model]
family = "smollm3"
hf_repo = "example/SmolLM3-3B"
revision = "988f1dde"
{files}'''

VM1SM3_TOML = '''
[vm1sm3]
repetitions = 2
replacement = "zebra"
system_fractions = [0.0, 0.5, 0.999]
tool_indexes = [0, 2]
edit_user_message = true
corpus_dir = "corpus/live/vm1sm3"
results_dir = "results/vm1sm3"
registered_by = "{registered}"
[vm1sm3.hypotheses.H-M1V8SM3]
block_size = 8
[vm1sm3.hypotheses.H-M1V16SM3]
block_size = 16
'''


def test_the_family_map_names_both_lanes_files_for_the_fourth_family_and_only_the_l_lane_for_qwen17():
    assert FAMILY_FILES["qwen17"] == ("l17.toml", None)
    assert FAMILY_FILES[FAMILY] == ("lsm3.toml", "vsm3.toml")


# --- llama.cpp lane --------------------------------------------------------------------------------

def _lsm3_world(tmp_path, *, lsm3_registered="0051", m1sm3_registered="0053", template=True):
    w = _lworld(tmp_path)
    root = w["root"]
    (root / "corpus" / "live" / "m1sm3").mkdir(parents=True)
    (root / "corpus" / "live" / "controls").mkdir(parents=True, exist_ok=True)
    model = root / "model-sm3.gguf"
    model.write_bytes(b"other bytes standing in for the 3B gguf")
    tpl = root / "chat_template.jinja"
    tpl.write_text("{{ messages }}", encoding="utf-8")
    pin = TEMPLATE_PIN.format(sha=sha256_file_bytes(tpl)) if template else ""
    (root / "config" / "lsm3.toml").write_text(
        LSM3_TOML.format(registered=lsm3_registered, sha=sha256_file_bytes(model), template=pin), encoding="utf-8")
    (root / "config" / "m1sm3.toml").write_text(M1SM3_TOML.format(registered=m1sm3_registered), encoding="utf-8")
    w.update(model_sm3=model, lsm3=load_l17_config(root / "config" / "lsm3.toml"),
             m1sm3=load_m1sm3_config(root / "config" / "m1sm3.toml", root))
    return w


def test_the_family_file_loads_by_its_stem_with_an_optional_chat_template_pin(tmp_path):
    w = _lsm3_world(tmp_path)
    assert w["lsm3"].model.family == FAMILY and w["lsm3"].registered_by == "0051"
    assert w["lsm3"].chat_template is not None
    assert w["lsm3"].chat_template.revision == "486a602f" and w["lsm3"].chat_template.file == "chat_template.jinja"
    w2 = _lsm3_world(tmp_path / "b", template=False)
    assert w2["lsm3"].chat_template is None
    # l17.toml keeps loading through the same function: the table is the file's stem
    l17 = load_l17_config(__import__("prefix_mortality").REPO_ROOT / "config" / "l17.toml")
    assert l17.model.family == "qwen17" and l17.chat_template is None


def test_an_m1sm3_id_must_carry_the_family_suffix(tmp_path):
    p = tmp_path / "m1sm3.toml"
    p.write_text(M1SM3_TOML.format(registered="0053").replace("H-M1L1SM3", "H-M1L1Q17"), encoding="utf-8")
    with pytest.raises(ValueError, match="then SM3 for the family"):
        load_m1sm3_config(p, tmp_path)


def test_m1_on_the_fourth_family_pins_its_file_under_its_stem_and_the_summarizer_expects_it(tmp_path):
    w = _lsm3_world(tmp_path)
    with lserve("faithful", slots=1) as (url, _):
        report = m1_run(w["m1sm3"], w["controls"], w["engine"], FAMILY, "H-M1L1SM3", LClient(url, 30.0),
                        w["model_sm3"], repo_root=w["root"], fixture=w["root"] / "fixture", l17=w["lsm3"])
    assert report["outcome"] == "ALL MATCH"
    assert [t["site"] for t in report["trials"]] == SITES * 2
    records = read(w["m1sm3"].corpus_dir / f"{report['run_id']}.jsonl")
    want = {"controls": sha256_text_file(w["controls"].config_path),
            "engines": sha256_text_file(w["engine"].config_path),
            "m1sm3": sha256_text_file(w["m1sm3"].config_path),
            "lsm3": sha256_text_file(w["lsm3"].config_path)}
    assert all(r["config_sha256"] == want and r["experiment"] == "m1sm3" for r in records)
    assert all(r["model_file"] == "model-sm3.gguf" and r["model_sha256"] == w["lsm3"].model.sha256 for r in records)
    again, text = summarize_m1(report["run_id"], repo_root=w["root"])
    assert again == report and "H-M1L1SM3" in text


def test_controls_on_the_fourth_family_pin_its_file_and_summarize(tmp_path):
    w = _lsm3_world(tmp_path)
    with lserve("faithful", slots=1) as (url, _):
        report = controls_run(w["controls"], w["engine"], FAMILY, LClient(url, 30.0), w["model_sm3"],
                              repo_root=w["root"], fixture=w["root"] / "fixture", l17=w["lsm3"])
    assert report["verdict"] == "PASS"
    records = read(w["controls"].corpus_dir / f"{report['run_id']}.jsonl")
    assert all(r["config_sha256"]["lsm3"] == sha256_text_file(w["lsm3"].config_path) for r in records)
    assert all("l17" not in r["config_sha256"] for r in records)
    again, _ = summarize_controls(report["run_id"], repo_root=w["root"])
    assert again == report


@pytest.mark.parametrize("kw,needle", [
    ({"lsm3_registered": ""}, "lsm3.toml is UNREGISTERED"),
    ({"m1sm3_registered": ""}, "m1sm3.toml is UNREGISTERED"),
])
def test_an_unregistered_family_or_experiment_file_refuses_and_records_nothing(tmp_path, kw, needle):
    w = _lsm3_world(tmp_path, **kw)
    with lserve("faithful", slots=1) as (url, _):
        with pytest.raises(Refusal, match=needle):
            m1_run(w["m1sm3"], w["controls"], w["engine"], FAMILY, "H-M1L1SM3", LClient(url, 30.0), w["model_sm3"],
                   repo_root=w["root"], fixture=w["root"] / "fixture", l17=w["lsm3"])
    assert not list(w["m1sm3"].corpus_dir.glob("*.jsonl"))


def test_an_unknown_family_is_refused_with_every_known_family_named(tmp_path):
    w = _lworld(tmp_path)
    with pytest.raises(Refusal, match="family files cover \\['qwen17', 'smollm3'\\]"):
        _maybe_l17(w["engine"], "granite")


# --- vLLM lane ------------------------------------------------------------------------------------

def _vsm3_world(tmp_path, *, vsm3_registered="0051", vm1sm3_registered="0053"):
    w = _vworld(tmp_path)
    root = w["root"]
    (root / "corpus" / "live" / "vm1sm3").mkdir(parents=True)
    (root / "corpus" / "live" / "vm1").mkdir(parents=True)
    (root / "config" / "vm1.toml").write_text(VM1.format(registered="0025"), encoding="utf-8")   # the repo always has it
    sm3_dir = root / "models-sm3"
    sm3_dir.mkdir()
    rows = []
    for name in ("model-00001-of-00002.safetensors", "config.json", "tokenizer.json", "chat_template.jinja"):
        p = sm3_dir / name
        p.write_bytes(f"sm3 bytes of {name}".encode())
        rows.append(f'[[vsm3.model.files]]\nname = "{name}"\nsha256 = "{sha256_file_bytes(p)}"\n')
    (root / "config" / "vsm3.toml").write_text(VSM3_TOML.format(registered=vsm3_registered, files="".join(rows)),
                                               encoding="utf-8")
    (root / "config" / "vm1sm3.toml").write_text(VM1SM3_TOML.format(registered=vm1sm3_registered), encoding="utf-8")
    w.update(model_dir_sm3=sm3_dir, vsm3=load_vfamily_config(root / "config" / "vsm3.toml"),
             vm1sm3=load_vm1_config(root / "config" / "vm1sm3.toml", root))
    return w


def test_the_v_family_file_loads_with_its_served_name_revision_and_files(tmp_path):
    w = _vsm3_world(tmp_path)
    v = w["vsm3"]
    assert v.served_model_name == "smollm3-3b" and v.registered_by == "0051"
    assert v.model.family == FAMILY and v.model.revision == "988f1dde"
    assert [f.name for f in v.model.files][-1] == "chat_template.jinja"
    # vllm.toml's own model keeps loading, revision empty where none was pinned
    assert w["vllm"].model("qwen17").revision == ""
    assert [h.id for h in w["vm1sm3"].hypotheses] == ["H-M1V8SM3", "H-M1V16SM3"]


def test_v_controls_on_the_fourth_family_gate_the_served_name_pin_the_files_and_summarize(tmp_path):
    w = _vsm3_world(tmp_path)
    with vserve("faithful", block_size=8, served="smollm3-3b") as (url, _):
        report = vcontrols_run(w["controls"], w["vllm"], FAMILY, 8, VClient(url, 30.0), w["model_dir_sm3"],
                               repo_root=w["root"], fixture=w["root"] / "fixture", vfam=w["vsm3"])
    assert report["verdict"] == "PASS", report["failures"] + report["unmeasurable"]
    records = read(w["vllm"].corpus_dir / f"{report['run_id']}.jsonl")
    want = {"controls": sha256_text_file(w["controls"].config_path), "vllm": sha256_text_file(w["vllm"].config_path),
            "vsm3": sha256_text_file(w["vsm3"].config_path)}
    assert all(r["config_sha256"] == want and r["served_model_name"] == "smollm3-3b" for r in records)
    assert all(r["model_hf_repo"] == "example/SmolLM3-3B" and len(r["model_files"]) == 4 for r in records)
    again, _ = summarize_vcontrols(report["run_id"], repo_root=w["root"])
    assert again == report


def test_v_controls_refuse_a_server_that_serves_another_name_for_the_family(tmp_path):
    w = _vsm3_world(tmp_path)
    with vserve("faithful", block_size=8) as (url, _):   # serves qwen3-1.7b
        with pytest.raises(Refusal, match="config pins 'smollm3-3b'"):
            vcontrols_run(w["controls"], w["vllm"], FAMILY, 8, VClient(url, 30.0), w["model_dir_sm3"],
                          repo_root=w["root"], fixture=w["root"] / "fixture", vfam=w["vsm3"])
    assert not list(w["vllm"].corpus_dir.glob("*.jsonl"))


def test_v_controls_refuse_the_other_familys_model_dir_by_hash(tmp_path):
    w = _vsm3_world(tmp_path)
    with vserve("faithful", block_size=8, served="smollm3-3b") as (url, _):
        with pytest.raises(Refusal, match="does not exist|hashes to"):
            vcontrols_run(w["controls"], w["vllm"], FAMILY, 8, VClient(url, 30.0), w["model_dir"],
                          repo_root=w["root"], fixture=w["root"] / "fixture", vfam=w["vsm3"])


def test_vm1_on_the_fourth_family_writes_its_own_experiment_and_family_hashes_and_summarizes(tmp_path):
    w = _vsm3_world(tmp_path)
    with vserve("faithful", block_size=8, served="smollm3-3b") as (url, _):
        report = vm1_run(w["vm1sm3"], w["controls"], w["vllm"], FAMILY, "H-M1V8SM3", VClient(url, 30.0),
                         w["model_dir_sm3"], repo_root=w["root"], fixture=w["root"] / "fixture", vfam=w["vsm3"])
    assert report["outcome"] == "ALL MATCH", report
    records = read(w["vm1sm3"].corpus_dir / f"{report['run_id']}.jsonl")
    want = {"controls": sha256_text_file(w["controls"].config_path), "vllm": sha256_text_file(w["vllm"].config_path),
            "vm1sm3": sha256_text_file(w["vm1sm3"].config_path), "vsm3": sha256_text_file(w["vsm3"].config_path)}
    assert all(r["config_sha256"] == want and r["experiment"] == "vm1sm3" for r in records)
    again = summarize_vm1(report["run_id"], repo_root=w["root"])
    assert again == report


def test_an_unregistered_v_family_file_refuses_before_the_server_is_contacted(tmp_path):
    w = _vsm3_world(tmp_path, vsm3_registered="")
    with pytest.raises(Refusal, match="vsm3.toml is UNREGISTERED"):
        vcontrols_run(w["controls"], w["vllm"], FAMILY, 8, VClient("http://127.0.0.1:9", 1.0), w["model_dir_sm3"],
                      repo_root=w["root"], fixture=w["root"] / "fixture", vfam=w["vsm3"])


def test_an_unknown_v_family_is_refused_with_the_known_ones_named(tmp_path):
    w = _vworld(tmp_path)
    with pytest.raises(Refusal, match="family files cover \\['smollm3'\\]"):
        _maybe_vfamily(w["vllm"], "granite")


def test_the_qwen17_v_records_keep_their_two_hash_keys(tmp_path):
    """The sealed V records carry exactly controls + vllm; the family mechanism must not add a key."""
    w = _vworld(tmp_path)
    with vserve("faithful", block_size=8) as (url, _):
        report = vcontrols_run(w["controls"], w["vllm"], "qwen17", 8, VClient(url, 30.0), w["model_dir"],
                               repo_root=w["root"], fixture=w["root"] / "fixture")
    records = read(w["vllm"].corpus_dir / f"{report['run_id']}.jsonl")
    assert all(set(r["config_sha256"]) == {"controls", "vllm"} for r in records)
    json.dumps(report)  # the report stays serialisable
