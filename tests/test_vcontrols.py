"""The V controls: the block arithmetic holds on a stand-in that follows the reading, including at
block boundaries; a run goes red on a stand-in that breaks a rule; the gates refuse an unregistered
config, a wrong version, a missing model and an unpinned block size; the summarizer recomputes from
disk and refuses edits; and the probe records nothing."""
import json

import pytest

from prefix_mortality.config import load_controls_config, load_vllm_config
from prefix_mortality.controls import Refusal
from prefix_mortality.hashing import sha256_file_bytes
from prefix_mortality.record import read
from prefix_mortality.summarize_vcontrols import evaluate, prediction, summarize
from prefix_mortality.vcontrols import build_body, probe, run
from prefix_mortality.vllm import Client, observed
from tests.fake_vllm import Engine, serve

SYSTEM = " ".join(f"Rule {i}: an agent must check the booking before it changes flight {i * 7}." for i in range(40))
TOOLS = [{"type": "function", "function": {"name": f"tool_{i}", "description": f"Look booking {i} up.",
                                           "parameters": {"type": "object", "properties": {"id": {"type": "string"}}}}}
         for i in range(3)]
VERSION, SERVED = "0.31.1rc1.dev8+gb6d8e8afd", "qwen3-1.7b"

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


def _vllm_toml(registered: str, files: list, blocks: str = "[8, 16]") -> str:
    rows = "\n".join(f'[[vllm.models.files]]\nname = "{n}"\nsha256 = "{s}"\n' for n, s in files)
    return f'''
[vllm]
repo = "https://github.com/vllm-project/vllm"
commit = "b6d8e8afd985f5711eee68e343d2ce908d166488"
version = "{VERSION}"
served_model_name = "{SERVED}"
dtype = "bfloat16"
max_model_len = 16384
kvcache_space_gib = 4
block_sizes = {blocks}
corpus_dir = "corpus/live/vcontrols"
results_dir = "results/vcontrols"
registered_by = "{registered}"
[[vllm.models]]
family = "qwen17"
hf_repo = "Qwen/Qwen3-1.7B"
{rows}'''


def _world(tmp_path, *, registered="0022", blocks="[8, 16]"):
    root = tmp_path / "repo"
    for d in ("config", "corpus/live/vcontrols", "corpus/requests", "results", "fixture", "models"):
        (root / d).mkdir(parents=True)
    files = []
    for name in ("model-a.safetensors", "config.json"):
        p = root / "models" / name
        p.write_bytes(f"bytes of {name}".encode())
        files.append((name, sha256_file_bytes(p)))
    (root / "fixture" / "system.txt").write_text(SYSTEM, encoding="utf-8")
    (root / "fixture" / "tools.json").write_text(json.dumps(TOOLS), encoding="utf-8")
    (root / "config" / "controls.toml").write_text(CONTROLS, encoding="utf-8")
    (root / "config" / "vllm.toml").write_text(_vllm_toml(registered, files, blocks), encoding="utf-8")
    return {"root": root, "model_dir": root / "models",
            "controls": load_controls_config(root / "config" / "controls.toml", root),
            "vllm": load_vllm_config(root / "config" / "vllm.toml", root)}


def _run(tmp_path, *, block=8, mode="faithful", engine_block=None, registered="0022", **kw):
    w = _world(tmp_path, registered=registered, **kw)
    with serve(mode, block_size=engine_block if engine_block is not None else block) as (url, engine):
        report = run(w["controls"], w["vllm"], "qwen17", block, Client(url, 30.0), w["model_dir"],
                     repo_root=w["root"], fixture=w["root"] / "fixture")
    return w, report, engine


def _n(messages_system, user, tools=TOOLS):
    e = Engine()
    return len(e.tokenize(e.render([{"role": "system", "content": messages_system},
                                    {"role": "user", "content": user}], tools)))


def test_the_rule_at_and_off_the_boundaries():
    assert prediction("write", 604, 128, 1) == {"cached": 0, "created": 512}, "the smoke's reading"
    assert prediction("read", 604, 128, 1) == {"cached": 512, "created": 0}
    assert prediction("write", 512, 128, 1) == {"cached": 0, "created": 512}, "n a multiple: every block is full"
    assert prediction("read", 512, 128, 1) == {"cached": 384, "created": 128}, "the hit is capped at n - 1"
    assert prediction("write", 511, 128, 1) == {"cached": 0, "created": 511}, "n + 1 a multiple: the tail fills with the generated token"
    assert prediction("read", 511, 128, 1) == {"cached": 384, "created": 127}
    assert prediction("scramble", 604, 128, 1) == {"cached": 0, "created": 512}


def test_the_controls_pass_and_the_write_side_is_measured(tmp_path):
    w, report, engine = _run(tmp_path, block=8)
    assert report["verdict"] == "PASS", report["failures"] + report["unmeasurable"]
    assert report["block_size"] == 8 and report["generated_tokens"] == 1 and len(report["repetitions"]) == 2
    for row in report["repetitions"]:
        wr, rd, sc = row["write"], row["read"], row["scramble"]
        assert wr["usage_cached_tokens"] == 0 and wr["usage_created_cache_tokens"] == prediction("write", wr["n"], 8, 1)["created"] > 0
        assert rd["usage_cached_tokens"] == prediction("read", rd["n"], 8, 1)["cached"] >= rd["n"] - 8
        assert sc["usage_cached_tokens"] == 0 and abs(sc["n"] - wr["n"]) <= 16
        assert all(row[c]["checks"] and all(row[c]["checks"].values()) for c in ("write", "read", "scramble"))
    records = read(w["vllm"].corpus_dir / f"{report['run_id']}.jsonl")
    assert len(records) == 6 and {r["block_size"] for r in records} == {8}
    assert report["run_id"].endswith("-qwen17-b8")
    assert {r["server"]["version"] for r in records} == {VERSION}
    recomputed, text = summarize(report["run_id"], w["root"])
    assert recomputed == report and "block 8): PASS" in text


def test_boundary_prompts_pass_end_to_end(tmp_path):
    pads = {}
    for j in range(2):                                        # "!" adds one token, " pad" adds two
        for k in range(8):
            user = "Hello." + "!" * j + " pad" * k
            pads.setdefault(_n(f"run {'0' * 32}\n{SYSTEM}", user) % 8, user)
    assert 0 in pads and 7 in pads, f"no pad hits the boundaries; residues found {sorted(pads)}"
    for residue in (0, 7):                                    # n % B == 0, and (n + 1) % B == 0
        w = _world(tmp_path / f"r{residue}")
        w["controls"] = w["controls"].__class__(**{**w["controls"].__dict__, "user_message": pads[residue]})
        with serve("faithful", block_size=8) as (url, _):
            report = run(w["controls"], w["vllm"], "qwen17", 8, Client(url, 30.0), w["model_dir"],
                         repo_root=w["root"], fixture=w["root"] / "fixture")
        ns = {row["write"]["n"] % 8 for row in report["repetitions"]}
        assert ns == {residue} and report["verdict"] == "PASS", (residue, report["failures"])


@pytest.mark.parametrize("mode, verdict, reason", [
    ("no_details", "NOT MEASURABLE", "the server reported no usage_cached_tokens, usage_created_cache_tokens"),
    ("no_cache", "FAIL", "read: cached_as_predicted is false"),
    ("sticky", "FAIL", "write: cached_as_predicted is false"),
])
def test_a_run_goes_red_on_an_engine_that_breaks_a_rule(tmp_path, mode, verdict, reason):
    w, report, _ = _run(tmp_path, mode=mode)
    assert report["verdict"] == verdict
    assert any(reason in x for x in report["failures"] + report["unmeasurable"]), report
    assert len(read(w["vllm"].corpus_dir / f"{report['run_id']}.jsonl")) == 3, "the run stops at the first red repetition"
    assert summarize(report["run_id"], w["root"])[0]["verdict"] == verdict


def test_a_server_at_another_block_size_fails_the_arithmetic(tmp_path):
    w, report, _ = _run(tmp_path, block=16, engine_block=8)      # registered 16, server running at 8
    assert report["verdict"] == "FAIL"
    assert any("as_predicted is false" in x for x in report["failures"])


def test_run_refuses_unregistered_bad_version_missing_model_and_unpinned_block(tmp_path):
    def go(w, url, block=8):
        return run(w["controls"], w["vllm"], "qwen17", block, Client(url, 30.0), w["model_dir"],
                   repo_root=w["root"], fixture=w["root"] / "fixture")
    w = _world(tmp_path / "a", registered="")
    with serve() as (url, _):
        with pytest.raises(Refusal, match="vllm.toml is UNREGISTERED"):
            go(w, url)
    w = _world(tmp_path / "b")
    with pytest.raises(Refusal, match="block size 5 is not registered"):
        go(w, "http://127.0.0.1:1", 5)
    (w["model_dir"] / "config.json").write_bytes(b"tampered")
    with pytest.raises(Refusal, match="hashes to"):
        go(w, "http://127.0.0.1:1")
    w = _world(tmp_path / "c")
    with serve(version="0.99.0") as (url, _):
        with pytest.raises(Refusal, match="reports version '0.99.0'"):
            go(w, url)
    with serve(served="other-model") as (url, _):
        with pytest.raises(Refusal, match="serves \\['other-model'\\]"):
            go(w, url)
    assert not list((w["root"] / "corpus" / "live" / "vcontrols").iterdir()), "a refused run records nothing"
    assert not list((w["root"] / "corpus" / "requests").iterdir())


def test_the_summarizer_recomputes_and_refuses_edits(tmp_path):
    w, report, _ = _run(tmp_path)
    log = w["vllm"].corpus_dir / f"{report['run_id']}.jsonl"
    requests_dir = w["root"] / "corpus" / "requests"

    def changed(change):
        records = read(log)
        change(records)
        return evaluate(records, requests_dir, w["vllm"].block_sizes, 1, 16)

    assert changed(lambda rs: None) == report, "untouched records reproduce the report"
    shared = changed(lambda rs: rs[2].update(request_sha256=rs[0]["request_sha256"], nonce=rs[0]["nonce"]))
    assert "repetition 1 scramble: nonce_isolates_first_block is false" in shared["failures"], \
        "a scramble that shares the write's tokens is caught by the isolation check"
    inflated = changed(lambda rs: rs[0]["observed"].update(usage_prompt_tokens=rs[0]["observed"]["usage_prompt_tokens"] + 1))
    assert "repetition 1 write: size_agrees is false" in inflated["failures"], \
        "a reported prompt size that is not the stored token count is caught"
    moved = changed(lambda rs: rs[1]["observed"].update(usage_cached_tokens=rs[1]["observed"]["usage_cached_tokens"] - 8))
    assert "repetition 1 read: cached_as_predicted is false" in moved["failures"]
    with pytest.raises(ValueError, match="block size 7 is not registered"):
        changed(lambda rs: [r.update(block_size=7) for r in rs])
    with pytest.raises(ValueError, match="records mix values of block_size"):
        changed(lambda rs: rs[0].update(block_size=16))
    original = log.read_text(encoding="utf-8")

    def rewrite(change):
        records = read(log)
        change(records)
        log.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8")

    rewrite(lambda rs: rs[1]["observed"].update(usage_cached_tokens=rs[1]["observed"]["usage_cached_tokens"] - 1))
    with pytest.raises(ValueError, match="do not reproduce the driver's report"):
        summarize(report["run_id"], w["root"])
    log.write_text(original, encoding="utf-8")
    assert summarize(report["run_id"], w["root"])[0] == report
    toml = w["root"] / "config" / "vllm.toml"
    toml.write_text(toml.read_text(encoding="utf-8").replace("kvcache_space_gib = 4", "kvcache_space_gib = 8"), encoding="utf-8")
    with pytest.raises(ValueError, match="different config"):
        summarize(report["run_id"], w["root"])


def test_probe_reports_the_block_facts_and_records_nothing(tmp_path):
    w = _world(tmp_path, registered="")
    with serve(block_size=16) as (url, _):
        out = probe(w["controls"], w["vllm"], Client(url, 30.0), fixture=w["root"] / "fixture", pad_words=3)
    assert out["server"]["version"] == VERSION and out["pad_words"] == 3
    assert out["nonce_in_rendered"] is True
    assert 0 < out["shared_head_tokens_across_nonces"] < 16, "the header is real and under one block"
    n = out["prompt_tokens"]
    assert out["n_mod"] == {"8": n % 8, "16": n % 16}
    assert out["write"]["usage_cached_tokens"] == 0
    assert out["read"]["usage_cached_tokens"] == prediction("read", n, 16, 1)["cached"]
    assert out["fresh_nonce"]["usage_cached_tokens"] == 0, "a fresh nonce shares no full block"
    assert not list((w["root"] / "corpus" / "requests").iterdir()) and not list((w["root"] / "corpus" / "live" / "vcontrols").iterdir())


def test_client_prepare_matches_the_fake_and_observed_never_reads_zero(tmp_path):
    w = _world(tmp_path)
    body = build_body(w["controls"], SERVED, SYSTEM, TOOLS, "0" * 32)
    with serve(block_size=8) as (url, engine):
        client = Client(url, 30.0)
        p = client.prepare(body)
        assert "run " + "0" * 32 in p["rendered"] and len(p["tokens"]) == len(engine.tokenize(p["rendered"]))
        assert "".join(t["piece"] for t in p["tokens"]) != p["rendered"], "V pieces are BPE-internal; they do not join to the text"
        assert client.count_text("three words here") == 5     # 3 words + 2 spaces under the fake's tokenizer
    assert observed({"usage": {"prompt_tokens": 9}}) == {
        "usage_prompt_tokens": 9, "usage_cached_tokens": None, "usage_created_cache_tokens": None}
    assert observed({}) == {"usage_prompt_tokens": None, "usage_cached_tokens": None, "usage_created_cache_tokens": None}
