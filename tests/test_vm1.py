"""Edit position on V: the block formulas hold on the stand-in, a run goes red on a stand-in that
breaks a rule or sits at another block size, the gates refuse an unregistered config and an unpinned
block, the summarizer recomputes everything from disk and refuses edits, and the probe records
nothing."""
import json

import pytest

from prefix_mortality.config import load_vm1_config
from prefix_mortality.controls import Refusal
from prefix_mortality.summarize_vm1 import prediction, summarize
from prefix_mortality.vm1 import probe, run
from prefix_mortality.vllm import Client
from tests.fake_vllm import Engine, serve
from tests.test_vcontrols import SYSTEM, TOOLS, _n, _world

VM1 = '''
[vm1]
repetitions = 2
replacement = "zebra"
system_fractions = [0.0, 0.5, 0.999]
tool_indexes = [0, 2]
edit_user_message = true
corpus_dir = "corpus/live/vm1"
results_dir = "results/vm1"
registered_by = "{registered}"
[vm1.hypotheses.H-M1V8]
block_size = 8
[vm1.hypotheses.H-M1V16]
block_size = 16
'''


def _vm1_world(tmp_path, *, registered="0025", vregistered="0022", blocks="[8, 16]"):
    w = _world(tmp_path, registered=vregistered, blocks=blocks)
    (w["root"] / "corpus" / "live" / "vm1").mkdir(parents=True)
    (w["root"] / "config" / "vm1.toml").write_text(VM1.format(registered=registered), encoding="utf-8")
    w["vm1"] = load_vm1_config(w["root"] / "config" / "vm1.toml", w["root"])
    return w


def _go(w, url, hid="H-M1V8"):
    return run(w["vm1"], w["controls"], w["vllm"], "qwen17", hid, Client(url, 30.0), w["model_dir"],
               repo_root=w["root"], fixture=w["root"] / "fixture")


def _run_vm1(tmp_path, *, hid="H-M1V8", mode="faithful", engine_block=None, **kw):
    w = _vm1_world(tmp_path, **kw)
    block = w["vm1"].hypothesis(hid).block_size
    with serve(mode, block_size=engine_block if engine_block is not None else block) as (url, engine):
        report = _go(w, url, hid)
    return w, report, engine


def test_prediction_is_the_block_formula_at_and_off_the_boundaries():
    base = list(range(600))
    mid = base[:300] + [9999] + base[301:]                      # d = 300
    assert prediction(base, mid, 128) == {"first_differing_token": 300, "predicted_cached": 256,
                                          "predicted_created": 512 - 256}
    at = base[:512] + [9999] + base[513:]                       # d = 512, a multiple
    assert prediction(base, at, 128) == {"first_differing_token": 512, "predicted_cached": 512,
                                         "predicted_created": 0}
    last = base[:599] + [9999]                                  # d = n - 1: the cap bites nothing new
    assert prediction(base, last, 128) == {"first_differing_token": 599, "predicted_cached": 512,
                                           "predicted_created": 0}
    first = [9999] + base[1:]                                   # d = 0: everything dies
    assert prediction(base, first, 128) == {"first_differing_token": 0, "predicted_cached": 0,
                                            "predicted_created": 512}
    whole = base + [9999]                                       # d = n of base; cap at n - 1 of edited
    assert prediction(base, whole, 128)["predicted_cached"] == 512
    # d = n (a pure prefix of the base) at a block multiple: the n - 1 cap bites. A word replacement
    # never produces this (the edit diverges before the end), but the registered rule carries the cap
    # and the summarizer must apply it, or a hit of n would be predicted where the server recomputes
    # the last token.
    assert prediction(base, base[:512], 128) == {"first_differing_token": 512, "predicted_cached": 384,
                                                 "predicted_created": 128}


def test_a_run_matches_on_the_faithful_stand_in_and_d_orders_the_sites(tmp_path):
    w, report, _ = _run_vm1(tmp_path)
    assert report["outcome"] == "ALL MATCH" and report["matching_trials"] == report["trial_count"] == 12
    by_site = {t["site"]: t for t in report["trials"] if t["repetition"] == 1}
    ds = [by_site[s]["first_differing_token"] for s in ("system-0.000", "system-0.500", "system-0.999")]
    assert ds == sorted(ds) and ds[0] < ds[2], "an earlier edit differs earlier"
    assert by_site["user"]["predicted_cached"] >= by_site["system-0.000"]["predicted_cached"]
    for t in report["trials"]:
        assert t["observed_cached"] == t["predicted_cached"] == (min(t["first_differing_token"], t["n"] - 1) // 8) * 8
    assert summarize(report["run_id"], repo_root=w["root"]) == report
    report16 = None
    with serve(block_size=16) as (url, _):
        report16 = _go(w, url, "H-M1V16")
    assert report16["outcome"] == "ALL MATCH" and report16["block_size"] == 16


def test_red_modes_and_a_server_at_another_block_size_go_red(tmp_path):
    w, report, _ = _run_vm1(tmp_path / "a", mode="no_details")
    assert report["outcome"] == "NOT MEASURABLE" and report["trial_count"] == 1, "the run halts"
    w, report, _ = _run_vm1(tmp_path / "b", mode="sticky")
    assert report["outcome"] == "FAILED CONTROL" and "not isolated" in report["failures"][0]
    w, report, _ = _run_vm1(tmp_path / "c", mode="no_cache")
    assert report["outcome"] == "MISMATCH" and report["trial_count"] == 12, "a mismatch is a result; the run goes on"
    assert report["matching_trials"] < 12
    n = _n(f"run {'0' * 32}\n{SYSTEM}", "Hello.")
    assert n % 16 >= 8, "premise: at this fixture the two block sizes disagree on the write rule"
    w, report, _ = _run_vm1(tmp_path / "d", engine_block=16)
    assert report["outcome"] == "FAILED CONTROL" and "write rule" in report["failures"][0]


def test_gates_refuse_before_anything_is_recorded(tmp_path):
    w = _vm1_world(tmp_path / "a", registered="")
    with serve() as (url, _):
        with pytest.raises(Refusal, match="vm1.toml is UNREGISTERED"):
            _go(w, url)
    w = _vm1_world(tmp_path / "b")
    with pytest.raises(ValueError, match="registers no hypothesis 'H-M1V99'"):
        _go(w, "http://127.0.0.1:1", "H-M1V99")
    w = _vm1_world(tmp_path / "c", blocks="[16, 32]")
    with pytest.raises(Refusal, match="block size 8 is not registered"):
        _go(w, "http://127.0.0.1:1", "H-M1V8")
    assert not list((w["root"] / "corpus" / "live" / "vm1").iterdir()), "a refused run records nothing"
    assert not list((w["root"] / "corpus" / "requests").iterdir())


def test_the_summarizer_refuses_a_rewritten_record_report_or_config(tmp_path):
    w, report, _ = _run_vm1(tmp_path)
    log = next((w["root"] / "corpus" / "live" / "vm1").glob("*.jsonl"))
    rows = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
    kept = log.read_text(encoding="utf-8")
    rows[1]["observed"]["usage_cached_tokens"] += 8
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not reproduce the driver's report"):
        summarize(report["run_id"], repo_root=w["root"])
    log.write_text(kept, encoding="utf-8")
    rows = [json.loads(l) for l in kept.splitlines()]
    rows[1]["predicted_cached"] += 8
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not reproduce the driver's report"):
        summarize(report["run_id"], repo_root=w["root"])
    log.write_text(kept, encoding="utf-8")
    cfg = w["root"] / "config" / "vm1.toml"
    cfg.write_text(cfg.read_text(encoding="utf-8").replace("repetitions = 2", "repetitions = 3"),
                   encoding="utf-8")
    with pytest.raises(ValueError, match="different config"):
        summarize(report["run_id"], repo_root=w["root"])


def test_a_tampered_prediction_is_named_by_evaluate_trial(tmp_path):
    from prefix_mortality.summarize_vm1 import evaluate_trial
    w, report, _ = _run_vm1(tmp_path)
    log = next((w["root"] / "corpus" / "live" / "vm1").glob("*.jsonl"))
    rows = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
    rows[1]["predicted_cached"] += 8
    t = evaluate_trial(rows[0], rows[1], None, w["root"] / "corpus" / "requests", 8)
    assert any("stored prediction" in f for f in t["failures"])


def test_probe_records_nothing_and_matches(tmp_path):
    w = _vm1_world(tmp_path)
    with serve(block_size=8) as (url, _):
        out = probe(w["vm1"], w["controls"], w["vllm"], "H-M1V8", ["system-0.000", "user"],
                    Client(url, 30.0), fixture=w["root"] / "fixture")
    assert [t["match"] for t in out["trials"]] == [True, True]
    assert out["block_size"] == 8 and out["trials"][0]["first_differing_token"] <= out["trials"][1]["first_differing_token"]
    assert not list((w["root"] / "corpus" / "live" / "vm1").iterdir())
    assert not list((w["root"] / "corpus" / "requests").iterdir())


def test_the_isolation_guard_fires_when_a_base_shares_a_full_block_with_the_previous_one(tmp_path):
    from prefix_mortality.summarize_vm1 import evaluate_trial
    w, report, _ = _run_vm1(tmp_path)
    log = next((w["root"] / "corpus" / "live" / "vm1").glob("*.jsonl"))
    rows = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
    from prefix_mortality.record import load_request
    base_ids = [t["id"] for t in load_request(w["root"] / "corpus" / "requests",
                                              rows[0]["request_sha256"])["tokens"]]
    t = evaluate_trial(rows[0], rows[1], base_ids, w["root"] / "corpus" / "requests", 8)
    assert any("shares a full block" in f for f in t["failures"]), "a prior base equal to this one must trip the guard"
    t = evaluate_trial(rows[0], rows[1], base_ids[:4] + [-1], w["root"] / "corpus" / "requests", 8)
    assert t["failures"] == [] and t["match"] is True
