"""Adapted from lag-ladder tests/test_config.py: the seal cases are verbatim; the pilot cases are
replaced by the controls and engines loaders."""
import pytest

from prefix_mortality.config import load_controls_config, load_engines_config, load_m1_config, load_seal_config


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


def test_repo_configs_load():
    from prefix_mortality import ENGINE_SHA, REPO_ROOT
    m1 = load_m1_config(REPO_ROOT / "config" / "m1.toml", REPO_ROOT)
    assert m1.registered_by == "", "the m1 config is registered: update this test with the entry number"
    assert m1.corpus_dir.parent == REPO_ROOT / "corpus" / "live"
    assert {(h.id, h.slots, h.rule) for h in m1.hypotheses} == {("H-M1L1", 1, "prefix"), ("H-M1LD", 4, "threshold")}
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
