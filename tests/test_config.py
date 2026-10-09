"""Adapted from lag-ladder tests/test_config.py: the seal cases are verbatim; the pilot cases are
replaced by the controls and engines loaders."""
import pytest

from prefix_mortality.config import (load_controls_config, load_engines_config, load_m1_config, load_m2_config,
                                     load_m3_config, load_m4_config, load_m7_config,
                                     load_seal_config, load_vllm_config)


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_seal_config_expands_upstream_and_resolves_relative_to_root(tmp_path):
    p = _write(tmp_path, "seal.toml", '''
predictions_dir = "ledger/predictions"
upstream_path = "../up"
[[artifact_roots]]
path = "mappers"
pattern = "{pair}/**/k*.safetensors"
[[artifact_roots]]
path = "${upstream}/mappers"
pattern = "{pair}/**/k*.safetensors"
''')
    cfg = load_seal_config(p, repo_root=tmp_path / "repo")
    assert cfg.predictions_dir == (tmp_path / "repo" / "ledger" / "predictions")
    assert cfg.artifact_roots[0].path == tmp_path / "repo" / "mappers"
    assert cfg.artifact_roots[1].path == (tmp_path / "repo" / ".." / "up" / "mappers").resolve()
    assert "{pair}" in cfg.artifact_roots[1].pattern


def test_seal_config_refuses_pattern_without_pair_placeholder(tmp_path):
    p = _write(tmp_path, "seal.toml", '''
predictions_dir = "ledger/predictions"
upstream_path = "../up"
[[artifact_roots]]
path = "mappers"
pattern = "**/k*.safetensors"
''')
    with pytest.raises(ValueError, match="{pair}"):
        load_seal_config(p, repo_root=tmp_path)


CONTROLS = '''
[controls]
repetitions = 5
length_tolerance_tokens = 16
max_tokens = 1
temperature = 0.0
nonce_bytes = 16
seed = 7
request_timeout_seconds = 600.0
user_message = "Hello."
corpus_dir = "corpus/live/controls"
results_dir = "results/controls"
registered_by = ""
'''


def test_controls_config_loads_and_records_unregistered(tmp_path):
    cfg = load_controls_config(_write(tmp_path, "controls.toml", CONTROLS), repo_root=tmp_path)
    assert cfg.repetitions == 5 and cfg.length_tolerance_tokens == 16 and cfg.nonce_bytes == 16 and cfg.seed == 7
    assert cfg.max_tokens == 1 and cfg.temperature == 0.0 and cfg.user_message == "Hello."
    assert cfg.corpus_dir == tmp_path / "corpus" / "live" / "controls"
    assert cfg.registered_by == ""


@pytest.mark.parametrize("old, new, msg", [
    ("repetitions = 5", "repetitions = 0", "repetitions"),
    ("repetitions = 5", "repetitions = 5.0", "repetitions"),
    ("temperature = 0.0", "temperature = -1.0", "temperature"),
    ("nonce_bytes = 16", "nonce_bytes = 0", "nonce_bytes"),
    ("max_tokens = 1", "max_tokens = 0", "max_tokens"),
    ("seed = 7", "seed = true", "seed"),
    ('user_message = "Hello."', 'user_message = ""', "user_message"),
    ('registered_by = ""', 'registered_by = "12"', "four-digit"),
    ("max_tokens = 1\n", "", "missing"),
    ("seed = 7", "seed = 7\nsurprise = 1", "unknown keys"),
])
def test_controls_config_refuses_bad_values(tmp_path, old, new, msg):
    assert CONTROLS.count(old) == 1
    with pytest.raises(ValueError, match=msg):
        load_controls_config(_write(tmp_path, "controls.toml", CONTROLS.replace(old, new)), repo_root=tmp_path)


ENGINES = '''
[engine.llamacpp]
repo = "https://github.com/ggml-org/llama.cpp"
release = "b11235"
commit = "6c7a87f7e5e5cd75b8a641c3471f2dee84a6ed17"
download = "llama-b11235-bin-macos-arm64.tar.gz"
download_sha256 = "d28351029acd7e0c01825d8e7dddadded3da4a2494bf72ebd98e73aec9344d50"
registered_by = ""
[[engine.llamacpp.models]]
family = "qwen"
hf_repo = "Qwen/Qwen3-8B-GGUF"
file = "Qwen3-8B-Q4_K_M.gguf"
sha256 = "d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785"
[[engine.llamacpp.models]]
family = "llama"
hf_repo = "bartowski/Meta-Llama-3.1-8B-Instruct-GGUF"
file = "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
sha256 = "7b064f5842bf9532c91456deda288a1b672397a54fa729aa665952863033557c"
'''


def test_engines_config_loads_and_finds_a_model_by_family(tmp_path):
    e = load_engines_config(_write(tmp_path, "engines.toml", ENGINES))["llamacpp"]
    assert e.release == "b11235" and e.commit.startswith("6c7a87f") and e.registered_by == ""
    assert [m.family for m in e.models] == ["qwen", "llama"]
    assert e.model("llama").file == "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
    with pytest.raises(ValueError, match="no model of family"):
        e.model("mistral")


@pytest.mark.parametrize("old, new, msg", [
    ('commit = "6c7a87f7e5e5cd75b8a641c3471f2dee84a6ed17"', 'commit = "6c7a87f"', "commit"),
    ('commit = "6c7a87f7e5e5cd75b8a641c3471f2dee84a6ed17"', 'commit = "LLAMACPP_SHA_PENDING"', "commit"),
    ('sha256 = "d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785"', 'sha256 = ""', "sha256"),
    ('release = "b11235"', 'release = ""', "release"),
    ('release = "b11235"\n', "", "missing"),
    ('registered_by = ""', 'registered_by = ""\n[engine.llamacpp.flags]\ncache_reuse = 0', "unknown keys"),
    ('family = "llama"', 'family = "qwen"', "distinct families"),
    ('registered_by = ""', 'registered_by = "1"', "four-digit"),
])
def test_engines_config_refuses_bad_values(tmp_path, old, new, msg):
    assert ENGINES.count(old) == 1
    with pytest.raises(ValueError, match=msg):
        load_engines_config(_write(tmp_path, "engines.toml", ENGINES.replace(old, new)))


M1 = '''
[m1]
repetitions = 5
replacement = "zebra"
system_fractions = [0, 0.25, 0.999]
tool_indexes = [0, 13]
edit_user_message = true
similarity_threshold = 0.10
threshold_margin = 0.002
corpus_dir = "corpus/live/m1"
results_dir = "results/m1"
registered_by = ""
[m1.hypotheses.H-M1L1]
slots = 1
rule = "prefix"
[m1.hypotheses.H-M1LD]
slots = 4
rule = "threshold"
'''


def test_m1_config_loads_and_finds_a_hypothesis(tmp_path):
    cfg = load_m1_config(_write(tmp_path, "m1.toml", M1), repo_root=tmp_path)
    assert cfg.repetitions == 5 and cfg.replacement == "zebra" and cfg.edit_user_message is True
    assert cfg.system_fractions == (0.0, 0.25, 0.999) and cfg.tool_indexes == (0, 13)
    assert cfg.similarity_threshold == 0.10 and cfg.threshold_margin == 0.002 and cfg.registered_by == ""
    assert cfg.corpus_dir == tmp_path / "corpus" / "live" / "m1"
    assert [(h.id, h.slots, h.rule) for h in cfg.hypotheses] == [("H-M1L1", 1, "prefix"), ("H-M1LD", 4, "threshold")]
    assert cfg.hypothesis("H-M1LD").rule == "threshold"
    with pytest.raises(ValueError, match="registers no hypothesis"):
        cfg.hypothesis("H-M1LV")


@pytest.mark.parametrize("old, new, msg", [
    ("repetitions = 5", "repetitions = 0", "repetitions"),
    ('replacement = "zebra"', 'replacement = "two words"', "one word"),
    ("system_fractions = [0, 0.25, 0.999]", "system_fractions = [0.25, 0.25]", "strictly ascending"),
    ("system_fractions = [0, 0.25, 0.999]", "system_fractions = [0.5, 1.5]", "system_fractions"),
    ("tool_indexes = [0, 13]", "tool_indexes = [13, 0]", "strictly ascending"),
    ("tool_indexes = [0, 13]", "tool_indexes = [0.5]", "tool_indexes"),
    ("edit_user_message = true", 'edit_user_message = "yes"', "true or false"),
    ("similarity_threshold = 0.10", "similarity_threshold = 1.5", "between 0 and 1"),
    ("threshold_margin = 0.002", "threshold_margin = -1", "threshold_margin"),
    ("threshold_margin = 0.002\n", "", "missing"),
    ('registered_by = ""', 'registered_by = ""\ncache_ram = 0', "unknown keys"),
    ('registered_by = ""', 'registered_by = "6"', "four-digit"),
    ('rule = "prefix"', 'rule = "nearest"', "rule must be one of"),
    ("slots = 1", "slots = 0", "slots"),
    ("slots = 1", 'slots = 1\nflag = "--parallel 1"', "unknown keys"),
    ("[m1.hypotheses.H-M1L1]", "[m1.hypotheses.H-M1A1]", "an id is H-M1L"),
])
def test_m1_config_refuses_bad_values(tmp_path, old, new, msg):
    assert M1.count(old) == 1
    with pytest.raises(ValueError, match=msg):
        load_m1_config(_write(tmp_path, "m1.toml", M1.replace(old, new)), repo_root=tmp_path)


def test_m1_config_refuses_a_file_that_names_no_site_or_no_hypothesis(tmp_path):
    none = M1.replace("[0, 0.25, 0.999]", "[]").replace("[0, 13]", "[]").replace("= true", "= false")
    with pytest.raises(ValueError, match="names no site"):
        load_m1_config(_write(tmp_path, "m1.toml", none), repo_root=tmp_path)
    bare = M1[:M1.index("[m1.hypotheses.H-M1L1]")] + "[m1.hypotheses]\n"
    with pytest.raises(ValueError, match="registers no hypothesis"):
        load_m1_config(_write(tmp_path, "m1.toml", bare), repo_root=tmp_path)


M7 = '''
[m7]
repetitions = 3
k_schedule = [0, 1, 12]
cache_ram_mib = 8192
corpus_dir = "corpus/live/m7"
results_dir = "results/m7"
registered_by = ""
[m7.kv_geometry.qwen]
n_layer = 36
n_head_kv = 8
head_dim = 128
bytes_per_value = 2
[m7.hypotheses.H-M7LD]
slots = 4
'''


def test_m7_config_loads_and_sizes_a_prompt(tmp_path):
    cfg = load_m7_config(_write(tmp_path, "m7.toml", M7), repo_root=tmp_path)
    assert cfg.repetitions == 3 and cfg.k_schedule == (0, 1, 12) and cfg.cache_ram_mib == 8192
    assert cfg.cache_limit_bytes == 8192 * 1024 * 1024 and cfg.registered_by == ""
    assert cfg.bytes_per_token("qwen") == 36 * 2 * 8 * 128 * 2 == 147456
    assert [(h.id, h.slots) for h in cfg.hypotheses] == [("H-M7LD", 4)]
    with pytest.raises(ValueError, match="registers no hypothesis"):
        cfg.hypothesis("H-M7L1")
    with pytest.raises(ValueError, match="no kv_geometry for family"):
        cfg.bytes_per_token("llama")


@pytest.mark.parametrize("old, new, msg", [
    ("k_schedule = [0, 1, 12]", "k_schedule = [0, 12, 1]", "strictly ascending"),
    ("k_schedule = [0, 1, 12]", "k_schedule = [-1, 0]", "strictly ascending"),
    ("k_schedule = [0, 1, 12]", "k_schedule = []", "names no K"),
    ("cache_ram_mib = 8192", "cache_ram_mib = 0", "cache_ram_mib must be an int >= 1"),
    ("cache_ram_mib = 8192", "cache_ram_mib = 8192\nextra = 1", "unknown keys"),
    ("n_layer = 36", "n_layer = 0", "n_layer must be an int >= 1"),
    ("n_layer = 36\n", "", "is missing"),
    ("[m7.hypotheses.H-M7LD]", "[m7.hypotheses.H-M7A1]", "an id is H-M7L"),
    ("slots = 4", "slots = 0", "slots must be an int >= 1"),
])
def test_m7_config_refuses_bad_values(tmp_path, old, new, msg):
    assert M7.count(old) == 1
    with pytest.raises(ValueError, match=msg):
        load_m7_config(_write(tmp_path, "m7.toml", M7.replace(old, new)), repo_root=tmp_path)


def test_m7_config_refuses_a_file_with_no_geometry_or_no_hypothesis(tmp_path):
    bare = M7[:M7.index("[m7.kv_geometry.qwen]")] + "[m7.kv_geometry]\n[m7.hypotheses.H-M7LD]\nslots = 4\n"
    with pytest.raises(ValueError, match="has no kv_geometry"):
        load_m7_config(_write(tmp_path, "m7.toml", bare), repo_root=tmp_path)
    none = M7[:M7.index("[m7.hypotheses.H-M7LD]")] + "[m7.hypotheses]\n"
    with pytest.raises(ValueError, match="registers no hypothesis"):
        load_m7_config(_write(tmp_path, "m7.toml", none), repo_root=tmp_path)


def test_repo_configs_load():
    from prefix_mortality import ENGINE_SHA, REPO_ROOT
    m1 = load_m1_config(REPO_ROOT / "config" / "m1.toml", REPO_ROOT)
    assert m1.registered_by == "0006"
    assert m1.corpus_dir.parent == REPO_ROOT / "corpus" / "live"
    assert {(h.id, h.slots, h.rule) for h in m1.hypotheses} == {("H-M1L1", 1, "prefix"), ("H-M1LD", 4, "threshold")}
    m7 = load_m7_config(REPO_ROOT / "config" / "m7.toml", REPO_ROOT)
    assert m7.registered_by == "0012"
    assert m7.k_schedule == (0, 1, 4, 8, 10, 11, 12, 13, 16) and m7.cache_ram_mib == 8192 and m7.repetitions == 3
    assert m7.bytes_per_token("qwen") == 147456 and m7.bytes_per_token("llama") == 131072
    assert [(h.id, h.slots) for h in m7.hypotheses] == [("H-M7LD", 4)]
    m2 = load_m2_config(REPO_ROOT / "config" / "m2.toml", REPO_ROOT)
    assert m2.registered_by == "0015"
    assert [c.id for c in m2.changes] == ["S1", "S2", "S3", "S4", "S5", "S6"]
    assert [(c.id, c.reading) for c in m2.changes if c.reading == "differs"] == [("S3", "differs"), ("S4", "differs")]
    assert [(h.id, h.slots, h.rule) for h in m2.hypotheses] == [("H-M2L1", 1, "prefix")]
    m3 = load_m3_config(REPO_ROOT / "config" / "m3.toml", REPO_ROOT)
    assert m3.registered_by == "0015"
    assert m3.base_kwargs == {"date_string": "01 Oct 2026", "enable_thinking": True}
    assert [(c.id, c.key, c.value) for c in m3.changes] == [("T1", "date_string", "02 Oct 2026"), ("T2", "enable_thinking", False)]
    assert {(h.id, h.slots, h.rule) for h in m3.hypotheses} == {("H-M3L1", 1, "prefix"), ("H-M3LD", 4, "threshold")}
    seal = load_seal_config(REPO_ROOT / "config" / "seal.toml", REPO_ROOT)
    for root in seal.artifact_roots:
        assert root.path.is_dir(), f"{root.path} must exist in a fresh clone: the seal writer fails closed on it"
    controls = load_controls_config(REPO_ROOT / "config" / "controls.toml", REPO_ROOT)
    assert controls.registered_by == "0002"
    assert controls.corpus_dir.parent == REPO_ROOT / "corpus" / "live"
    engine = load_engines_config(REPO_ROOT / "config" / "engines.toml")["llamacpp"]
    assert engine.registered_by == "0002"
    assert engine.commit == ENGINE_SHA
    assert {m.family for m in engine.models} == {"qwen", "llama"}
    m4 = load_m4_config(REPO_ROOT / "config" / "m4.toml", REPO_ROOT)
    assert m4.registered_by == "0019"
    assert m4.sleep_margin_seconds == 5
    assert [(h.id, h.slots, h.sleep_idle_seconds, h.gaps, h.repetitions) for h in m4.hypotheses] == [
        ("H-M4LD", 4, -1, (0, 2, 4, 60, 600), 2), ("H-M4LS", 4, 60, (20, 100), 3)]
    v = load_vllm_config(REPO_ROOT / "config" / "vllm.toml", REPO_ROOT)
    assert v.registered_by == "0022"
    assert v.commit == "b6d8e8afd985f5711eee68e343d2ce908d166488" and v.commit[:7] in v.version
    assert v.block_sizes == (32, 128) and v.served_model_name == "qwen3-1.7b" and v.dtype == "bfloat16"
    assert v.kvcache_space_gib == 4 and v.max_model_len == 16384
    assert [(m.family, len(m.files)) for m in v.models] == [("qwen17", 4)]
    assert v.corpus_dir == REPO_ROOT / "corpus" / "live" / "vcontrols"


M2 = '''
[m2]
repetitions = 5
corpus_dir = "corpus/live/m2"
results_dir = "results/m2"
registered_by = ""
[m2.changes.S1]
reading = "identical"
[m2.changes.S3]
reading = "differs"
[m2.hypotheses.H-M2L1]
slots = 1
rule = "prefix"
'''

M3 = '''
[m3]
repetitions = 5
similarity_threshold = 0.10
threshold_margin = 0.002
corpus_dir = "corpus/live/m3"
results_dir = "results/m3"
registered_by = ""
[m3.base_kwargs]
date_string = "01 Oct 2026"
enable_thinking = true
tools_in_user_message = false
[m3.changes.T1]
key = "date_string"
value = "02 Oct 2026"
[m3.changes.T2]
key = "enable_thinking"
value = false
[m3.hypotheses.H-M3L1]
slots = 1
rule = "prefix"
[m3.hypotheses.H-M3LD]
slots = 4
rule = "threshold"
'''


def test_m2_config_loads(tmp_path):
    cfg = load_m2_config(_write(tmp_path, "m2.toml", M2), repo_root=tmp_path)
    assert cfg.repetitions == 5 and cfg.registered_by == ""
    assert [(c.id, c.reading) for c in cfg.changes] == [("S1", "identical"), ("S3", "differs")]
    assert cfg.change("S3").reading == "differs"
    assert [(h.id, h.slots, h.rule) for h in cfg.hypotheses] == [("H-M2L1", 1, "prefix")]
    with pytest.raises(ValueError, match="registers no hypothesis"):
        cfg.hypothesis("H-M2LD")
    with pytest.raises(ValueError, match="registers no change"):
        cfg.change("S2")


@pytest.mark.parametrize("old, new, msg", [
    ("[m2.changes.S1]", "[m2.changes.S9]", "not a registered change id"),
    ('reading = "identical"', 'reading = "same"', "reading must be"),
    ("[m2.hypotheses.H-M2L1]", "[m2.hypotheses.H-M1L1]", "an id is H-M2L"),
    ('rule = "prefix"', 'rule = "nearest"', "rule must be one of"),
    ("repetitions = 5", "repetitions = 0", "repetitions must be an int >= 1"),
])
def test_m2_config_refuses_bad_values(tmp_path, old, new, msg):
    assert M2.count(old) == 1
    with pytest.raises(ValueError, match=msg):
        load_m2_config(_write(tmp_path, "m2.toml", M2.replace(old, new)), repo_root=tmp_path)


def test_m2_config_refuses_no_change_or_no_hypothesis(tmp_path):
    none = M2[:M2.index("[m2.changes.S1]")] + "[m2.changes]\n" + M2[M2.index("[m2.hypotheses.H-M2L1]"):]
    with pytest.raises(ValueError, match="registers no change"):
        load_m2_config(_write(tmp_path, "m2.toml", none), repo_root=tmp_path)
    bare = M2[:M2.index("[m2.hypotheses.H-M2L1]")] + "[m2.hypotheses]\n"
    with pytest.raises(ValueError, match="registers no hypothesis"):
        load_m2_config(_write(tmp_path, "m2.toml", bare), repo_root=tmp_path)


def test_m3_config_loads(tmp_path):
    cfg = load_m3_config(_write(tmp_path, "m3.toml", M3), repo_root=tmp_path)
    assert cfg.base_kwargs == {"date_string": "01 Oct 2026", "enable_thinking": True, "tools_in_user_message": False}
    assert [(c.id, c.key, c.value) for c in cfg.changes] == [("T1", "date_string", "02 Oct 2026"), ("T2", "enable_thinking", False)]
    assert cfg.similarity_threshold == 0.10 and cfg.threshold_margin == 0.002
    assert [(h.id, h.slots, h.rule) for h in cfg.hypotheses] == [("H-M3L1", 1, "prefix"), ("H-M3LD", 4, "threshold")]
    assert cfg.change("T2").value is False


@pytest.mark.parametrize("old, new, msg", [
    ('key = "date_string"', 'key = "colour"', "not in base_kwargs"),
    ('value = "02 Oct 2026"', 'value = "01 Oct 2026"', "equals the base value"),
    ("value = false", "value = 3", "must be a string or a boolean"),
    ("[m3.changes.T1]", "[m3.changes.X1]", "not a registered change id"),
    ("similarity_threshold = 0.10", "similarity_threshold = 1.5", "between 0 and 1"),
    ("[m3.hypotheses.H-M3LD]", "[m3.hypotheses.H-M3D]", "an id is H-M3L"),
])
def test_m3_config_refuses_bad_values(tmp_path, old, new, msg):
    assert M3.count(old) == 1
    with pytest.raises(ValueError, match=msg):
        load_m3_config(_write(tmp_path, "m3.toml", M3.replace(old, new)), repo_root=tmp_path)


M4 = '''
[m4]
sleep_margin_seconds = 5
corpus_dir = "corpus/live/m4"
results_dir = "results/m4"
registered_by = ""
[m4.hypotheses.H-M4LD]
slots = 4
sleep_idle_seconds = -1
gaps = [0, 30, 600]
repetitions = 2
[m4.hypotheses.H-M4LS]
slots = 4
sleep_idle_seconds = 60
gaps = [20, 100]
repetitions = 3
'''


def test_m4_config_loads_two_server_configurations(tmp_path):
    cfg = load_m4_config(_write(tmp_path, "m4.toml", M4), repo_root=tmp_path)
    assert cfg.sleep_margin_seconds == 5 and cfg.registered_by == ""
    assert cfg.corpus_dir == tmp_path / "corpus/live/m4" and cfg.results_dir == tmp_path / "results/m4"
    ld, ls = cfg.hypotheses
    assert (ld.id, ld.slots, ld.sleep_idle_seconds, ld.gaps, ld.repetitions, ld.sleeps) == ("H-M4LD", 4, -1, (0, 30, 600), 2, False)
    assert (ls.id, ls.slots, ls.sleep_idle_seconds, ls.gaps, ls.repetitions, ls.sleeps) == ("H-M4LS", 4, 60, (20, 100), 3, True)
    assert cfg.hypothesis("H-M4LS") is ls
    with pytest.raises(ValueError, match="registers no hypothesis 'H-M4L1'"):
        cfg.hypothesis("H-M4L1")


@pytest.mark.parametrize("old, new, msg", [
    ("gaps = [0, 30, 600]", "gaps = [30, 0, 600]", "strictly ascending"),
    ("gaps = [0, 30, 600]", "gaps = []", "names no gap"),
    ("sleep_idle_seconds = -1", "sleep_idle_seconds = 0", "must be -1 .no timer. or an int >= 1"),
    ("sleep_idle_seconds = -1", "sleep_idle_seconds = -2", "must be -1 .no timer. or an int >= 1"),
    ("sleep_idle_seconds = -1", "sleep_idle_seconds = true", "must be -1 .no timer. or an int >= 1"),
    ("gaps = [20, 100]", "gaps = [20, 63]", r"gaps \[63\] are within 5 s of the sleep threshold 60"),
    ("gaps = [20, 100]", "gaps = [56, 100]", r"gaps \[56\] are within 5 s of the sleep threshold 60"),
    ("gaps = [20, 100]", "gaps = [20, 60]", r"gaps \[60\] are within 5 s"),
    ("sleep_margin_seconds = 5", "sleep_margin_seconds = 0", "sleep_margin_seconds must be an int >= 1"),
    ("repetitions = 2", "repetitions = 0", "repetitions must be an int >= 1"),
    ("slots = 4\nsleep_idle_seconds = -1", "slots = 0\nsleep_idle_seconds = -1", "slots must be an int >= 1"),
    ("[m4.hypotheses.H-M4LD]", "[m4.hypotheses.H-M4A1]", "an id is H-M4L"),
    ('registered_by = ""', 'registered_by = ""\nextra = 1', "unknown keys"),
    ("repetitions = 3\n", "", "is missing"),
])
def test_m4_config_refuses_bad_values(tmp_path, old, new, msg):
    assert M4.count(old) == 1
    with pytest.raises(ValueError, match=msg):
        load_m4_config(_write(tmp_path, "m4.toml", M4.replace(old, new)), repo_root=tmp_path)


def test_m4_config_refuses_a_file_with_no_hypothesis(tmp_path):
    none = M4[:M4.index("[m4.hypotheses.H-M4LD]")] + "[m4.hypotheses]\n"
    with pytest.raises(ValueError, match="registers no hypothesis"):
        load_m4_config(_write(tmp_path, "m4.toml", none), repo_root=tmp_path)


VLLM = '''
[vllm]
repo = "https://github.com/vllm-project/vllm"
commit = "b6d8e8afd985f5711eee68e343d2ce908d166488"
version = "0.31.1rc1.dev8+gb6d8e8afd"
served_model_name = "m"
dtype = "bfloat16"
max_model_len = 16384
kvcache_space_gib = 4
block_sizes = [16, 128]
corpus_dir = "corpus/live/vcontrols"
results_dir = "results/vcontrols"
registered_by = ""
[[vllm.models]]
family = "qwen17"
hf_repo = "Qwen/Qwen3-1.7B"
[[vllm.models.files]]
name = "config.json"
sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
'''


def test_vllm_config_loads(tmp_path):
    cfg = load_vllm_config(_write(tmp_path, "vllm.toml", VLLM), repo_root=tmp_path)
    assert cfg.block_sizes == (16, 128) and cfg.model("qwen17").files[0].name == "config.json"
    with pytest.raises(ValueError, match="no model family 'x'"):
        cfg.model("x")


@pytest.mark.parametrize("old, new, msg", [
    ('version = "0.31.1rc1.dev8+gb6d8e8afd"', 'version = "0.31.1"', "does not carry the commit"),
    ("block_sizes = [16, 128]", "block_sizes = [128, 16]", "strictly ascending"),
    ("block_sizes = [16, 128]", "block_sizes = []", "names no block size"),
    ("kvcache_space_gib = 4", "kvcache_space_gib = 0", "must be an int >= 1"),
    ('sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"', 'sha256 = "zz"', "not a lowercase hex digest"),
    ('registered_by = ""', 'registered_by = ""\nextra = 1', "unknown keys"),
    ('served_model_name = "m"', "", "is missing"),
])
def test_vllm_config_refuses_bad_values(tmp_path, old, new, msg):
    assert VLLM.count(old) == 1
    with pytest.raises(ValueError, match=msg):
        load_vllm_config(_write(tmp_path, "vllm.toml", VLLM.replace(old, new)), repo_root=tmp_path)


def test_vllm_config_refuses_a_model_with_no_files(tmp_path):
    none = VLLM[:VLLM.index("[[vllm.models.files]]")]
    with pytest.raises(ValueError, match=r"is missing \['files'\]"):
        load_vllm_config(_write(tmp_path, "vllm.toml", none), repo_root=tmp_path)
