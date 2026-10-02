"""The controls pass on an engine that follows the two rules, and go red on one that breaks either."""
import json

import pytest

from prefix_mortality.config import load_controls_config, load_engines_config
from prefix_mortality.controls import Refusal, build_body, build_body_text, probe, run
from prefix_mortality.hashing import sha256_file_bytes
from prefix_mortality.llamacpp import Client, observed
from prefix_mortality.record import append, load_request, read, store_request
from prefix_mortality.serialize import tools_text
from prefix_mortality.summarize import header_tokens, summarize
from tests.fake_llamacpp import serve

SYSTEM = " ".join(f"Rule {i}: an agent must check the booking before it changes flight {i * 7}." for i in range(40))
TOOLS = [{"type": "function", "function": {"name": "get_booking", "description": "Look a booking up.",
                                           "parameters": {"type": "object", "properties": {"id": {"type": "string"}}}}}]


def _world(tmp_path, *, registered="0002", repetitions=2):
    root = tmp_path / "repo"
    for d in ("config", "corpus/live/controls", "corpus/requests", "results", "fixture"):
        (root / d).mkdir(parents=True)
    model = root / "model.gguf"
    model.write_bytes(b"not a model, only bytes to hash")
    (root / "fixture" / "system.txt").write_text(SYSTEM, encoding="utf-8")
    (root / "fixture" / "tools.json").write_text(json.dumps(TOOLS), encoding="utf-8")
    (root / "config" / "controls.toml").write_text(f'''
[controls]
repetitions = {repetitions}
length_tolerance_tokens = 16
max_tokens = 1
temperature = 0.0
nonce_bytes = 16
seed = 0
request_timeout_seconds = 30.0
user_message = "Hello."
corpus_dir = "corpus/live/controls"
results_dir = "results/controls"
registered_by = "{registered}"
''', encoding="utf-8")
    (root / "config" / "engines.toml").write_text(f'''
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
sha256 = "{sha256_file_bytes(model)}"
''', encoding="utf-8")
    cfg = load_controls_config(root / "config" / "controls.toml", root)
    engine = load_engines_config(root / "config" / "engines.toml")["llamacpp"]
    return root, cfg, engine, model


def _run(tmp_path, mode="faithful", **kw):
    root, cfg, engine, model = _world(tmp_path, **kw)
    with serve(mode) as (url, _):
        report = run(cfg, engine, "qwen", Client(url, cfg.request_timeout_seconds), model,
                     repo_root=root, fixture=root / "fixture")
    return root, cfg, report


def test_controls_pass_on_an_engine_that_follows_the_rules(tmp_path):
    root, cfg, report = _run(tmp_path)
    assert report["verdict"] == "PASS" and report["failures"] == [] and report["unmeasurable"] == []
    assert len(report["repetitions"]) == 2
    for row in report["repetitions"]:
        w, r, s = row["write"], row["read"], row["scramble"]
        assert r["cache_n"] == r["n"] - 1 and r["prompt_n"] == 1
        assert w["cache_n"] <= w["h"] < w["n"] and s["cache_n"] <= s["h"]
        assert abs(s["n"] - w["n"]) <= cfg.length_tolerance_tokens and s["request_sha256"] != w["request_sha256"]
    records = read(cfg.corpus_dir / f"{report['run_id']}.jsonl")
    assert [r["control"] for r in records] == ["write", "read", "scramble"] * 2
    assert len({r["nonce"] for r in records}) == 4                      # two per repetition, never repeated
    recomputed, text = summarize(report["run_id"], root)
    assert recomputed == report and "PASS" in text
    assert (cfg.results_dir / report["run_id"] / "summary.md").exists()


@pytest.mark.parametrize("mode, verdict, reason", [
    ("no_cache", "FAIL", "read: reuses_all_but_one is false"),
    ("sticky", "FAIL", "scramble: reuses_at_most_header is false"),
    ("no_fields", "NOT MEASURABLE", "the server reported no cache_n, prompt_n, usage_cached_tokens"),
])
def test_controls_go_red_and_stop_at_the_first_bad_repetition(tmp_path, mode, verdict, reason):
    root, cfg, report = _run(tmp_path, mode)
    assert report["verdict"] == verdict
    assert any(reason in x for x in report["failures"] + report["unmeasurable"]), report
    assert len(read(cfg.corpus_dir / f"{report['run_id']}.jsonl")) == 3
    recomputed, _ = summarize(report["run_id"], root)
    assert recomputed["verdict"] == verdict


def test_a_prompt_that_renders_differently_for_the_same_bytes_halts(tmp_path):
    # the stand-in's clock mode changes the rendered prompt on every call, as a date line does at midnight
    with pytest.raises(ValueError, match="rendered or tokenized differently"):
        _run(tmp_path, "clock")


def test_run_refuses_unregistered_config_wrong_model_and_wrong_build(tmp_path):
    root, cfg, engine, model = _world(tmp_path / "a", registered="")
    with serve() as (url, _):
        with pytest.raises(Refusal, match="UNREGISTERED"):
            run(cfg, engine, "qwen", Client(url, 30.0), model, repo_root=root, fixture=root / "fixture")
    root, cfg, engine, model = _world(tmp_path / "b")
    with serve(build_info="b11236-f1ea206") as (url, _):
        with pytest.raises(Refusal, match="config pins release b11235"):
            run(cfg, engine, "qwen", Client(url, 30.0), model, repo_root=root, fixture=root / "fixture")
    model.write_bytes(b"another file")
    with serve() as (url, _):
        with pytest.raises(Refusal, match="config pins"):
            run(cfg, engine, "qwen", Client(url, 30.0), model, repo_root=root, fixture=root / "fixture")
    assert not list((root / "corpus" / "live" / "controls").iterdir()), "a refused run records nothing"


def test_summarize_refuses_a_tampered_record_a_changed_config_and_a_changed_request(tmp_path):
    root, cfg, report = _run(tmp_path)
    log = cfg.corpus_dir / f"{report['run_id']}.jsonl"
    original = log.read_text(encoding="utf-8")
    records = read(log)

    records[1]["observed"]["cache_n"] -= 5                                # a read that reused less
    log.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8")
    with pytest.raises(ValueError, match="do not reproduce the driver's report"):
        summarize(report["run_id"], root)
    log.write_text(original, encoding="utf-8")
    assert summarize(report["run_id"], root)[0] == report                 # restored: accepted again

    stored = root / "corpus" / "requests" / f"{records[0]['request_sha256']}.json"
    kept = stored.read_text(encoding="utf-8")
    stored.write_text(kept.replace("Hello.", "Hallo."), encoding="utf-8")
    with pytest.raises(ValueError, match="does not hash to its own name"):
        summarize(report["run_id"], root)
    stored.write_text(kept, encoding="utf-8")

    toml = root / "config" / "controls.toml"
    toml.write_text(toml.read_text(encoding="utf-8").replace("length_tolerance_tokens = 16",
                                                              "length_tolerance_tokens = 9999"), encoding="utf-8")
    with pytest.raises(ValueError, match="different config"):
        summarize(report["run_id"], root)


def test_probe_reports_and_records_nothing(tmp_path):
    root, cfg, _, _ = _world(tmp_path, registered="")
    with serve() as (url, _):
        out = probe(cfg, Client(url, 30.0), fixture=root / "fixture")
    assert out["pieces_rebuild_the_rendered_prompt"] is True
    assert out["read"]["observed"]["cache_n"] == out["prompt_tokens"] - 1
    assert out["write"]["observed"]["cache_n"] <= out["header_bound"]
    assert not list((root / "corpus" / "requests").iterdir()) and not list((root / "corpus" / "live" / "controls").iterdir())


def test_header_bound_counts_tokens_that_start_before_the_nonce_ends():
    tokens = [{"id": i, "piece": p} for i, p in enumerate(["<sys>", "run", " ", "ab", "cd", "\n", "text"])]
    assert header_tokens(tokens, "abcd") == 5
    assert header_tokens(tokens, "ab") == 4
    with pytest.raises(ValueError, match="nonce is not in the rendered prompt"):
        header_tokens(tokens, "zz")


def test_a_field_the_server_did_not_report_is_none_not_zero():
    assert observed({"usage": {"prompt_tokens": 9}}) == {
        "cache_n": None, "prompt_n": None, "usage_prompt_tokens": 9, "usage_cached_tokens": None}
    assert observed({"timings": {"cache_n": 0, "prompt_n": 9}})["cache_n"] == 0
    assert observed({"timings": {"cache_n": True}})["cache_n"] is None


def test_request_store_is_content_addressed_and_refuses_a_conflict(tmp_path):
    body = b'{"messages":[]}'
    sha = store_request(tmp_path, body, "rendered", [{"id": 1, "piece": "rendered"}])
    assert store_request(tmp_path, body, "rendered", [{"id": 1, "piece": "rendered"}]) == sha
    assert load_request(tmp_path, sha)["body"] == body.decode()
    with pytest.raises(ValueError, match="rendered or tokenized differently"):
        store_request(tmp_path, body, "rendered otherwise", [{"id": 1, "piece": "rendered"}])
    with pytest.raises(ValueError, match="missing"):
        load_request(tmp_path, "0" * 64)


def test_log_is_append_only_lines_and_refuses_a_non_number(tmp_path):
    log = tmp_path / "x" / "run.jsonl"
    append(log, {"seq": 1, "observed": {"cache_n": None}})
    append(log, {"seq": 2, "observed": {"cache_n": 3}})
    assert [r["seq"] for r in read(log)] == [1, 2] and read(log)[0]["observed"]["cache_n"] is None
    with pytest.raises(ValueError):
        append(log, {"seq": 3, "x": float("nan")})
    assert len(read(log)) == 2


def _controls_cfg(tmp_path):
    p = tmp_path / "controls.toml"
    p.write_text('''
[controls]
repetitions = 1
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
''', encoding="utf-8")
    return load_controls_config(p, tmp_path)


def test_build_body_text_with_compact_tools_equals_build_body_byte_for_byte(tmp_path):
    cfg = _controls_cfg(tmp_path)
    tools = [{"type": "function", "function": {"name": "a", "description": "Look é up.", "parameters": {"type": "object"}}}]
    assert build_body_text(cfg, "sys", tools_text(tools), "ab" * 16) == build_body(cfg, "sys", tools, "ab" * 16)


def test_build_body_text_embeds_the_text_as_given_and_appends_template_kwargs(tmp_path):
    cfg = _controls_cfg(tmp_path)
    text = '[\n  {"type": "function", "function": {"name": "a"}}\n]'
    body = build_body_text(cfg, "sys", text, "ab" * 16, {"date_string": "01 Oct 2026", "tools_in_user_message": False})
    raw = body.decode("utf-8")
    assert text in raw and '"tools":' + text in raw
    parsed = json.loads(raw)
    assert list(parsed.keys()) == ["messages", "tools", "max_tokens", "temperature", "stream", "chat_template_kwargs"]
    assert parsed["chat_template_kwargs"] == {"date_string": "01 Oct 2026", "tools_in_user_message": False}
    assert "chat_template_kwargs" not in json.loads(build_body_text(cfg, "sys", text, "ab" * 16).decode("utf-8"))


def test_build_body_text_refuses_a_placeholder_collision(tmp_path):
    cfg = _controls_cfg(tmp_path)
    # quotes inside a JSON string are escaped, so a system text cannot collide with the marker
    assert build_body_text(cfg, 'the string "__TOOLS__" appears here', "[]", "ab" * 16)
    # a user message that is exactly the placeholder would: refused
    p = tmp_path / "controls.toml"
    p.write_text(p.read_text(encoding="utf-8").replace('user_message = "Hello."', 'user_message = "__TOOLS__"'), encoding="utf-8")
    with pytest.raises(ValueError, match="placeholder"):
        build_body_text(load_controls_config(p, tmp_path), "sys", "[]", "ab" * 16)
