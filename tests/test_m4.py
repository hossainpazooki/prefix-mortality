"""Idle expiry: at the defaults every gap keeps the prefix on a stand-in with no timer, a timer loses
it past the threshold, a server that ignores its flag fails a control, a death by time with no flag
is a mismatch (so the instrument can see one), a run goes red on a stand-in that breaks a rule, and
the summarizer reads the gap, the sleep state and the date from the records."""
import json

import pytest

from prefix_mortality.config import M4Hypothesis, load_controls_config, load_engines_config, load_m4_config
from prefix_mortality.controls import Refusal, build_body
from prefix_mortality.hashing import sha256_file_bytes
from prefix_mortality.llamacpp import Client
from prefix_mortality.m4 import probe, run
from prefix_mortality.record import read
from prefix_mortality.summarize_m4 import evaluate, prediction, summarize
from tests.fake_clock import FakeClock
from tests.fake_llamacpp import Engine, serve

SYSTEM = " ".join(f"Rule {i}: an agent must check the booking before it changes flight {i * 7}." for i in range(60))
TOOLS = [{"type": "function", "function": {"name": f"tool_{i}", "description": f"Look booking {i} up.",
                                           "parameters": {"type": "object", "properties": {"id": {"type": "string"}}}}}
         for i in range(3)]
GAPS_LD, GAPS_LS, S = (0, 30, 600), (20, 100), 60

CONTROLS = '''
[controls]
repetitions = 2
length_tolerance_tokens = 16
max_tokens = 1
temperature = 0.0
nonce_bytes = 16
seed = 0
request_timeout_seconds = 30.0
user_message = "Hello."
corpus_dir = "corpus/live/controls"
results_dir = "results/controls"
registered_by = "0002"
'''


def _m4_toml(registered: str) -> str:
    return f'''
[m4]
sleep_margin_seconds = 5
corpus_dir = "corpus/live/m4"
results_dir = "results/m4"
registered_by = "{registered}"
[m4.hypotheses.H-M4LD]
slots = 4
sleep_idle_seconds = -1
gaps = {list(GAPS_LD)}
repetitions = 2
[m4.hypotheses.H-M4LS]
slots = 4
sleep_idle_seconds = {S}
gaps = {list(GAPS_LS)}
repetitions = 2
'''


def _engines_toml(model_sha: str) -> str:
    return f'''
[engine.llamacpp]
repo = "https://github.com/ggml-org/llama.cpp"
release = "b11235"
commit = "6c7a87f7e5e5cd75b8a641c3471f2dee84a6ed17"
download = "llama-b11235-bin-macos-arm64.tar.gz"
download_sha256 = "{"d" * 64}"
registered_by = "0002"
[[engine.llamacpp.models]]
family = "qwen"
hf_repo = "example/model"
file = "model.gguf"
sha256 = "{model_sha}"
'''


def _prompt_tokens(controls) -> int:
    e = Engine()
    return len(e.tokenize(e.render(json.loads(build_body(controls, SYSTEM, TOOLS, "0" * 32)))))


def _world(tmp_path, *, registered="0019"):
    root = tmp_path / "repo"
    for d in ("config", "corpus/live/m4", "corpus/requests", "results", "fixture"):
        (root / d).mkdir(parents=True)
    model = root / "model.gguf"
    model.write_bytes(b"not a model, only bytes to hash")
    (root / "fixture" / "system.txt").write_text(SYSTEM, encoding="utf-8")
    (root / "fixture" / "tools.json").write_text(json.dumps(TOOLS), encoding="utf-8")
    (root / "config" / "controls.toml").write_text(CONTROLS, encoding="utf-8")
    (root / "config" / "m4.toml").write_text(_m4_toml(registered), encoding="utf-8")
    (root / "config" / "engines.toml").write_text(_engines_toml(sha256_file_bytes(model)), encoding="utf-8")
    controls = load_controls_config(root / "config" / "controls.toml", root)
    return {"root": root, "model": model, "n": _prompt_tokens(controls), "controls": controls,
            "m4": load_m4_config(root / "config" / "m4.toml", root),
            "engine": load_engines_config(root / "config" / "engines.toml")["llamacpp"]}


def _run(tmp_path, hid, *, mode="faithful", slots=4, sleep=-1, registered="0019", **engine_kw):
    w = _world(tmp_path, registered=registered)
    clock = FakeClock()
    with serve(mode, slots=slots, sleep_idle_seconds=sleep, clock=clock.seconds, **engine_kw) as (url, engine):
        report = run(w["m4"], w["controls"], w["engine"], "qwen", hid, Client(url, 30.0), w["model"],
                     repo_root=w["root"], fixture=w["root"] / "fixture", clock=clock)
    return w, report, engine, clock


def test_the_rule_on_the_registered_numbers():
    ld = M4Hypothesis("H-M4LD", 4, -1, (0, 30, 120, 600), 2)
    ls = M4Hypothesis("H-M4LS", 4, 60, (20, 100), 3)
    assert not ld.sleeps and ls.sleeps
    assert [prediction(ld, g, 4870) for g in ld.gaps] == [{"predicted_reuse": 4869, "server_sleeps": False}] * 4
    assert prediction(ls, 20, 4870) == {"predicted_reuse": 4869, "server_sleeps": False}
    assert prediction(ls, 100, 4870) == {"predicted_reuse": 0, "server_sleeps": True}
    assert prediction(ls, 61, 4870)["server_sleeps"] is True and prediction(ls, 60, 4870)["server_sleeps"] is False, \
        "the rule is strict at the threshold; the config keeps gaps away from it"


def test_at_the_defaults_every_gap_keeps_the_prefix(tmp_path):
    w, report, engine, clock = _run(tmp_path, "H-M4LD")
    assert report["outcome"] == "ALL MATCH", report["mismatches"] + report["failures"] + report["unmeasurable"]
    assert [t["gap_seconds"] for t in report["trials"]] == list(GAPS_LD) * 2 and engine.reloads == 0
    for t in report["trials"]:
        s = t["resend"]
        assert t["anchor"]["cache_n"] == 0 and s["n"] == w["n"]
        assert s["cache_n"] == s["predicted_reuse"] == w["n"] - 1
        assert s["server_sleeps"] is False and t["is_sleeping"] is False
        assert t["observed_gap_seconds"] == t["gap_seconds"]
    assert clock.slept == list(GAPS_LD) * 2, "the driver waited exactly the registered gaps"
    assert report["bracket"] == {"largest_gap_kept": 600, "smallest_gap_lost": None, "other_readings": []}
    assert [(g["gap_seconds"], g["counted"], g["kept"], g["lost"], g["slept"]) for g in report["by_gap"]] == [
        (0, 2, 2, 0, 0), (30, 2, 2, 0, 0), (600, 2, 2, 0, 0)]
    records = read(w["m4"].corpus_dir / f"{report['run_id']}.jsonl")
    assert len(records) == 2 * 2 * len(GAPS_LD) and [r["role"] for r in records][:4] == ["anchor", "resend", "anchor", "resend"]
    a, s = records[2], records[3]
    assert a["gap_seconds"] == s["gap_seconds"] == 30 and a["request_sha256"] == s["request_sha256"] and a["nonce"] == s["nonce"]
    assert a["seq"] + 1 == s["seq"] and "gap_probe" not in a and s["gap_probe"]["is_sleeping"] is False
    assert a["predicted_reuse"] == 0 and "server_sleeps" not in a and s["server_sleeps"] is False
    assert len({r["nonce"] for r in records}) == 2 * len(GAPS_LD), "one fresh nonce per trial"
    assert report["run_id"].endswith("-qwen-H-M4LD") and {r["server"]["n_ctx"] for r in records} == {8192}
    recomputed, text = summarize(report["run_id"], w["root"])
    assert recomputed == report and "ALL MATCH" in text and "largest gap kept: 600; smallest gap lost: none" in text


def test_with_a_timer_the_gap_past_it_loses_everything(tmp_path):
    w, report, engine, _ = _run(tmp_path, "H-M4LS", sleep=S)
    assert report["outcome"] == "ALL MATCH", report["mismatches"] + report["failures"] + report["unmeasurable"]
    assert engine.reloads == 2, "one reload per trial whose gap passed the threshold"
    for t in report["trials"]:
        s, past = t["resend"], t["gap_seconds"] > S
        assert s["server_sleeps"] is past and t["is_sleeping"] is past
        assert s["cache_n"] == s["predicted_reuse"] == (0 if past else s["n"] - 1)
    assert report["bracket"] == {"largest_gap_kept": 20, "smallest_gap_lost": 100, "other_readings": []}
    assert [(g["gap_seconds"], g["kept"], g["lost"], g["slept"]) for g in report["by_gap"]] == [(20, 2, 0, 0), (100, 0, 2, 2)]
    recomputed, text = summarize(report["run_id"], w["root"])
    assert recomputed == report and "--sleep-idle-seconds 60): ALL MATCH" in text


def test_a_server_that_ignores_its_flag_fails_a_control(tmp_path):
    w, report, engine, _ = _run(tmp_path, "H-M4LS", sleep=-1)        # registered to sleep at 60, started without the flag
    assert report["outcome"] == "FAILED CONTROL" and engine.reloads == 0
    assert report["failures"] == ["repetition 1 gap 100 s: sleep_state_as_predicted is false"]
    assert len(report["trials"]) == 2 and not report["mismatches"], "the run stops at the failed control"
    assert len(read(w["m4"].corpus_dir / f"{report['run_id']}.jsonl")) == 4
    assert summarize(report["run_id"], w["root"])[0]["outcome"] == "FAILED CONTROL"


def test_a_death_by_time_with_no_flag_is_a_mismatch_the_instrument_reads(tmp_path):
    w, report, engine, _ = _run(tmp_path, "H-M4LD", expire_after_seconds=100)    # no server at the pin does this
    assert report["outcome"] == "MISMATCH" and not report["failures"] and engine.reloads == 0
    assert {t["gap_seconds"] for t in report["trials"] if not t["match"]} == {600}
    assert all(t["is_sleeping"] is False for t in report["trials"]), "a slot that forgets is not a server that sleeps"
    assert len(report["trials"]) == 2 * len(GAPS_LD), "a prediction that is not met does not stop the run"
    assert report["bracket"] == {"largest_gap_kept": 30, "smallest_gap_lost": 600, "other_readings": []}
    assert summarize(report["run_id"], w["root"])[0]["outcome"] == "MISMATCH"


@pytest.mark.parametrize("mode, outcome, reason, records", [
    ("sticky", "FAILED CONTROL", "anchor_reuses_0 is false", 2),
    ("no_fields", "NOT MEASURABLE", "the server reported no cache_n, prompt_n, usage_cached_tokens", 2),
])
def test_a_run_goes_red_on_an_engine_that_breaks_a_rule(tmp_path, mode, outcome, reason, records):
    w, report, _, _ = _run(tmp_path, "H-M4LD", mode=mode)
    assert report["outcome"] == outcome
    assert any(reason in x for x in report["failures"] + report["unmeasurable"]), report
    assert len(read(w["m4"].corpus_dir / f"{report['run_id']}.jsonl")) == records
    assert summarize(report["run_id"], w["root"])[0]["outcome"] == outcome


def test_run_refuses_unregistered_wrong_slots_no_context_a_context_too_small_and_an_unknown_id(tmp_path):
    def go(w, url, hid="H-M4LD"):
        return run(w["m4"], w["controls"], w["engine"], "qwen", hid, Client(url, 30.0), w["model"],
                   repo_root=w["root"], fixture=w["root"] / "fixture", clock=FakeClock())
    w = _world(tmp_path / "a", registered="")
    with serve(slots=4) as (url, _):
        with pytest.raises(Refusal, match="m4.toml is UNREGISTERED"):
            go(w, url)
    w = _world(tmp_path / "b")
    with serve(slots=1) as (url, _):
        with pytest.raises(Refusal, match="requires a server reporting 4 slot"):
            go(w, url)
    with serve(slots=4, report_n_ctx=False) as (url, _):
        with pytest.raises(Refusal, match="reports no slot context"):
            go(w, url)
    with serve(slots=4, n_ctx=w["n"]) as (url, engine):
        with pytest.raises(Refusal, match=f"anchor \\({w['n']} tokens\\) does not fit the slot context \\({w['n']} tokens\\)"):
            go(w, url)
        assert engine.requests == 0, "nothing was sent"
    with serve(slots=4) as (url, engine):
        with pytest.raises(ValueError, match="registers no hypothesis 'H-M4LX'"):
            go(w, url, "H-M4LX")
        assert engine.requests == 0
    assert not list((w["root"] / "corpus" / "live" / "m4").iterdir()), "a refused run records nothing"
    assert not list((w["root"] / "corpus" / "requests").iterdir())


def test_the_summarizer_reads_the_gap_the_sleep_state_and_the_date_from_the_records(tmp_path):
    w, report, _, _ = _run(tmp_path, "H-M4LS", sleep=S)
    log = w["m4"].corpus_dir / f"{report['run_id']}.jsonl"
    requests_dir = w["root"] / "corpus" / "requests"

    def changed(change):
        records = read(log)
        change(records)
        return evaluate(records, requests_dir, w["m4"])

    assert changed(lambda rs: None) == report, "untouched records reproduce the report"
    early = changed(lambda rs: rs[1].update(ts_start=rs[0]["ts_end"]))              # the resend left before the gap
    assert early["outcome"] == "FAILED CONTROL" and early["failures"] == ["repetition 1 gap 20 s: gap_as_recorded is false"]
    late = changed(lambda rs: rs[1].update(ts_start=rs[3]["ts_start"]))             # 120 s after a 20 s gap: past the margin
    assert late["failures"] == ["repetition 1 gap 20 s: gap_as_recorded is false"]
    awake = changed(lambda rs: rs[3]["gap_probe"].update(is_sleeping=False))       # said awake after 100 s under the flag
    assert awake["failures"] == ["repetition 1 gap 100 s: sleep_state_as_predicted is false"]
    unread = changed(lambda rs: rs[3].update(gap_probe={}))
    assert unread["outcome"] == "NOT MEASURABLE"
    assert unread["unmeasurable"] == ["repetition 1 gap 100 s resend: the server reported no is_sleeping after the gap"]
    between = changed(lambda rs: rs[1].update(seq=rs[1]["seq"] + 1))
    assert between["failures"] == ["repetition 1 gap 20 s: nothing_between is false"]
    unstamped = changed(lambda rs: rs[1].update(ts_start="yesterday"))
    assert unstamped["outcome"] == "NOT MEASURABLE" and "no readable timestamps" in unstamped["unmeasurable"][0]
    dated = changed(lambda rs: rs[-1].update(local_date="1999-12-31"))
    assert dated["outcome"] == "NOT MEASURABLE" and "the local date changed during the trial" in dated["unmeasurable"][0]
    gone = changed(lambda rs: [r["server"].pop("n_ctx") for r in rs])
    assert gone["outcome"] == "NOT MEASURABLE" and all("reported no slot context" in x for x in gone["unmeasurable"])
    with pytest.raises(ValueError, match="a gap of 7 s is not registered for H-M4LS"):
        changed(lambda rs: rs[0].update(gap_seconds=7))
    with pytest.raises(ValueError, match="This run is not that experiment"):
        changed(lambda rs: [r["server"].update(total_slots=1) for r in rs])
    with pytest.raises(ValueError, match="repeated resend record"):
        changed(lambda rs: rs[0].update(role="resend"))


def test_summarize_refuses_a_changed_record_a_changed_prediction_and_a_changed_config(tmp_path):
    w, report, _, _ = _run(tmp_path, "H-M4LD")
    log = w["m4"].corpus_dir / f"{report['run_id']}.jsonl"
    original = log.read_text(encoding="utf-8")

    def rewrite(change):
        records = read(log)
        change(records)
        log.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8")

    rewrite(lambda rs: rs[1]["observed"].update(cache_n=rs[1]["observed"]["cache_n"] - 1))
    with pytest.raises(ValueError, match="do not reproduce the driver's report"):
        summarize(report["run_id"], w["root"])
    log.write_text(original, encoding="utf-8")
    rewrite(lambda rs: rs[1].update(predicted_reuse=0))                                 # a prediction moved after the fact
    with pytest.raises(ValueError, match="do not reproduce the driver's report"):
        summarize(report["run_id"], w["root"])
    log.write_text(original, encoding="utf-8")
    assert summarize(report["run_id"], w["root"])[0] == report
    toml = w["root"] / "config" / "m4.toml"
    toml.write_text(toml.read_text(encoding="utf-8").replace("sleep_margin_seconds = 5", "sleep_margin_seconds = 15"), encoding="utf-8")
    with pytest.raises(ValueError, match="different config"):
        summarize(report["run_id"], w["root"])


def test_probe_reports_each_gap_and_what_happened_inside_it_and_records_nothing(tmp_path):
    w = _world(tmp_path, registered="")
    clock = FakeClock()
    fixture = w["root"] / "fixture"
    with serve(slots=4, sleep_idle_seconds=S, clock=clock.seconds) as (url, engine):
        client = Client(url, 30.0)
        # props at 18 s: a timer restarted there would sleep at 78, so "asleep at 75" shows it was not restarted
        out = probe(w["m4"], w["controls"], "H-M4LS", "qwen", [20, 75], client, fixture=fixture, clock=clock, props_at=18)
        woken = probe(w["m4"], w["controls"], "H-M4LS", "qwen", [100], client, fixture=fixture, clock=clock, render_at=70)
        with pytest.raises(Refusal, match="inside every gap"):
            probe(w["m4"], w["controls"], "H-M4LS", "qwen", [20, 75], client, fixture=fixture, clock=clock, props_at=50)
        with pytest.raises(Refusal, match="0 or more"):
            probe(w["m4"], w["controls"], "H-M4LS", "qwen", [-1], client, fixture=fixture, clock=clock)
    short, long = out["trials"]
    assert out["server"]["total_slots"] == 4 and out["sleep_idle_seconds"] == S and out["slots_required"] == 4
    assert short["in_gap"] == [{"at": 18, "action": "props", "is_sleeping": False}]
    assert short["sleeping_after_the_gap"] is False and short["anchor_reuse"] == 0
    assert short["predicted_reuse"] == short["resend"]["cache_n"] == short["anchor_tokens"] - 1 and short["match"]
    assert long["in_gap"] == [{"at": 18, "action": "props", "is_sleeping": False}], "awake at 18 s"
    assert long["sleeping_after_the_gap"] is True, "asleep at 75 s: the props read at 18 s did not restart the timer"
    assert long["predicted_reuse"] == long["resend"]["cache_n"] == 0 and long["match"]
    (t,) = woken["trials"]
    assert t["in_gap"] == [{"at": 70, "action": "render", "is_sleeping": False}], "a render at 70 s woke the sleeping server"
    assert t["sleeping_after_the_gap"] is False and t["resend"]["cache_n"] == 0, "and the sleep before it had emptied everything"
    assert t["match"], "the prediction counts the sleep, not the state at the resend"
    assert engine.reloads == 2
    assert not list((w["root"] / "corpus" / "requests").iterdir()) and not list((w["root"] / "corpus" / "live" / "m4").iterdir())
