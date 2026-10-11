"""Templating (vm3) and serialization drift (vm2) on V: the arm constructions behave as the probe of
2026-10-11 recorded (thinking-off appends, thinking-on and both vm2 rewritings render identically),
the one registered formula prices every arm on the faithful stand-in, the gates refuse an
unregistered config, the summarizer resolves the experiment and refuses foreign arms, and the probe
records nothing."""
import json

import pytest

from prefix_mortality.config import load_vm2_config, load_vm3_config
from prefix_mortality.controls import Refusal
from prefix_mortality.record import read
from prefix_mortality.summarize_vm23 import summarize
from prefix_mortality.vllm import Client
from prefix_mortality.vm23 import probe, run
from tests.fake_vllm import serve
from tests.test_vcontrols import _world

VM23 = '''
[{exp}]
repetitions = 2
arms = {arms}
corpus_dir = "corpus/live/{exp}"
results_dir = "results/{exp}"
registered_by = "{registered}"
[{exp}.hypotheses.H-M{n}V8]
block_size = 8
[{exp}.hypotheses.H-M{n}V16]
block_size = 16
'''


def _world23(tmp_path, exp, *, registered="0035", arms=None):
    w = _world(tmp_path, blocks="[8, 16]")
    n = exp[-1]
    arms = arms if arms is not None else ('["thinking-off", "thinking-on"]' if exp == "vm3"
                                          else '["keyorder", "properties"]')
    (w["root"] / "corpus" / "live" / exp).mkdir(parents=True)
    # the properties arm needs a tool with two or more properties; the shared test TOOLS have one each
    tools = json.loads((w["root"] / "fixture" / "tools.json").read_text(encoding="utf-8"))
    tools[1]["function"]["parameters"]["properties"]["extra"] = {"type": "string"}
    (w["root"] / "fixture" / "tools.json").write_text(json.dumps(tools), encoding="utf-8")
    (w["root"] / "config" / f"{exp}.toml").write_text(
        VM23.format(exp=exp, n=n, arms=arms, registered=registered), encoding="utf-8")
    loader = load_vm2_config if exp == "vm2" else load_vm3_config
    w[exp] = loader(w["root"] / "config" / f"{exp}.toml", w["root"])
    return w


def _go(w, exp, url, hid):
    return run(w[exp], w["controls"], w["vllm"], "qwen17", hid, Client(url, 30.0), w["model_dir"],
               repo_root=w["root"], fixture=w["root"] / "fixture")


@pytest.mark.parametrize("exp,hid", [("vm3", "H-M3V8"), ("vm2", "H-M2V8")])
def test_a_run_matches_on_the_faithful_stand_in(tmp_path, exp, hid):
    w = _world23(tmp_path, exp)
    with serve("faithful", block_size=8) as (url, _):
        report = _go(w, exp, url, hid)
    assert report["outcome"] == "ALL MATCH" and report["experiment"] == exp
    assert report["trial_count"] == 4 and report["matching_trials"] == 4
    for t in report["trials"]:
        if t["site"] == "thinking-off":
            # the variant appends after the generation prompt: base is a strict prefix
            assert t["first_differing_token"] == t["base_n"] < t["n"]
        elif t["site"] == "properties":
            # the template preserves property order: the render differs at the first reordered tool
            assert t["first_differing_token"] < t["n"]
        else:
            # identical render: d = n, and the cap prices it as an identical resend
            assert t["first_differing_token"] == t["n"] == t["base_n"]
            assert t["predicted_cached"] == ((t["n"] - 1) // 8) * 8


def test_vm2_variants_differ_in_bytes_while_rendering_identically(tmp_path):
    w = _world23(tmp_path, "vm2")
    with serve("faithful", block_size=8) as (url, _):
        report = _go(w, "vm2", url, "H-M2V8")
    records = read(w["vm2"].corpus_dir / f"{report['run_id']}.jsonl")
    for base, variant in zip(records[::2], records[1::2]):
        assert base["request_sha256"] != variant["request_sha256"]   # distinct stored bodies


def test_an_unregistered_config_refuses_and_records_nothing(tmp_path):
    w = _world23(tmp_path, "vm3", registered="")
    with serve("faithful", block_size=8) as (url, _):
        with pytest.raises(Refusal, match="vm3.toml is UNREGISTERED"):
            _go(w, "vm3", url, "H-M3V8")
    assert not list(w["vm3"].corpus_dir.glob("*.jsonl"))


def test_summarize_resolves_the_experiment_reproduces_and_refuses_a_foreign_arm(tmp_path):
    w = _world23(tmp_path, "vm3")
    with serve("faithful", block_size=8) as (url, _):
        report = _go(w, "vm3", url, "H-M3V8")
    assert summarize(report["run_id"], "vm3", repo_root=w["root"]) == report
    log = w["vm3"].corpus_dir / f"{report['run_id']}.jsonl"
    lines = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
    for r in lines:
        r["site"] = {"thinking-off": "keyorder", "thinking-on": "properties"}[r["site"]]
    tampered = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in lines)
    log.write_text(tampered, encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="unregistered arm"):
        summarize(report["run_id"], "vm3", repo_root=w["root"])


def test_a_mismatching_stand_in_is_a_result_not_a_halt(tmp_path):
    w = _world23(tmp_path, "vm3")
    with serve("no_cache", block_size=8) as (url, _):
        report = _go(w, "vm3", url, "H-M3V8")
    assert report["outcome"] == "MISMATCH" and report["trial_count"] == 4


def test_probe_records_nothing_and_reports_render_identity(tmp_path):
    w = _world23(tmp_path, "vm2")
    with serve("faithful", block_size=8) as (url, _):
        out = probe(w["vm2"], w["controls"], w["vllm"], "H-M2V8", ["keyorder"], Client(url, 30.0),
                    fixture=w["root"] / "fixture")
    assert out["trials"][0]["renders_identical"] is True and out["trials"][0]["match"] is True
    assert not list(w["vm2"].corpus_dir.glob("*.jsonl"))
    assert not list((w["root"] / "corpus" / "requests").glob("*.json"))
