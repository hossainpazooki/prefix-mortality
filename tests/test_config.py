"""Adapted from lag-ladder tests/test_config.py: the seal cases are verbatim; the pilot cases are
replaced by the controls and engines loaders."""
import pytest

from prefix_mortality.config import load_controls_config, load_engines_config, load_seal_config


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
settle_seconds = 2.0
length_tolerance_tokens = 0
max_retries = 0
retry_wait_seconds = 0.0
nonce_bytes = 16
seed = 7
corpus_dir = "corpus/live/controls"
results_dir = "results/controls"
registered_by = ""
'''


def test_controls_config_loads_and_records_unregistered(tmp_path):
    cfg = load_controls_config(_write(tmp_path, "controls.toml", CONTROLS), repo_root=tmp_path)
    assert cfg.repetitions == 5 and cfg.settle_seconds == 2.0 and cfg.nonce_bytes == 16 and cfg.seed == 7
    assert cfg.corpus_dir == tmp_path / "corpus" / "live" / "controls"
    assert cfg.registered_by == ""


@pytest.mark.parametrize("old, new, msg", [
    ("repetitions = 5", "repetitions = 0", "repetitions"),
    ("repetitions = 5", "repetitions = 5.0", "repetitions"),
    ("settle_seconds = 2.0", "settle_seconds = -1.0", "settle_seconds"),
    ("nonce_bytes = 16", "nonce_bytes = 0", "nonce_bytes"),
    ("seed = 7", "seed = true", "seed"),
    ('registered_by = ""', 'registered_by = "12"', "four-digit"),
    ("max_retries = 0\n", "", "missing"),
    ("seed = 7", "seed = 7\nsurprise = 1", "unknown keys"),
])
def test_controls_config_refuses_bad_values(tmp_path, old, new, msg):
    assert CONTROLS.count(old) == 1
    with pytest.raises(ValueError, match=msg):
        load_controls_config(_write(tmp_path, "controls.toml", CONTROLS.replace(old, new)), repo_root=tmp_path)


ENGINES = '''
[engine.llamacpp]
repo = "https://github.com/ggml-org/llama.cpp"
commit = "LLAMACPP_SHA_PENDING"
registered_by = ""
[engine.llamacpp.flags]
cache_prompt = true
cache_reuse = 0
cache_ram_mib = 0
ctx_size = 8192
parallel = 1
slot_prompt_similarity = 0.10
[[engine.llamacpp.models]]
family = "qwen"
hf_repo = "Qwen/Qwen3-8B-GGUF"
file = ""
sha256 = "QWEN_GGUF_SHA256_PENDING"
[[engine.llamacpp.models]]
family = "llama"
hf_repo = "bartowski/Meta-Llama-3.1-8B-Instruct-GGUF"
file = ""
sha256 = "LLAMA_GGUF_SHA256_PENDING"
'''


def test_engines_config_loads_with_placeholders_and_reports_unpinned(tmp_path):
    e = load_engines_config(_write(tmp_path, "engines.toml", ENGINES))["llamacpp"]
    assert [m.family for m in e.models] == ["qwen", "llama"]
    assert e.flags["cache_reuse"] == 0 and e.flags["parallel"] == 1
    assert e.registered_by == "" and not e.pinned and not e.models[0].pinned


def test_engines_config_is_pinned_only_when_every_pin_is_a_digest(tmp_path):
    text = (ENGINES.replace("LLAMACPP_SHA_PENDING", "a" * 40)
            .replace("QWEN_GGUF_SHA256_PENDING", "b" * 64))
    assert not load_engines_config(_write(tmp_path, "engines.toml", text))["llamacpp"].pinned
    text = text.replace("LLAMA_GGUF_SHA256_PENDING", "c" * 64)
    assert load_engines_config(_write(tmp_path, "engines.toml", text))["llamacpp"].pinned


@pytest.mark.parametrize("old, new, msg", [
    ('commit = "LLAMACPP_SHA_PENDING"', 'commit = "6c7a87f"', "neither a digest"),
    ('sha256 = "QWEN_GGUF_SHA256_PENDING"', 'sha256 = ""', "neither a digest"),
    ("cache_reuse = 0\n", "", "missing"),
    ("cache_reuse = 0", "cache_reuse = 0\nmlock = true", "unknown keys"),
    ("cache_prompt = true", "cache_prompt = 1", "cache_prompt must be bool"),
    ("parallel = 1", "parallel = true", "parallel must be int"),
    ('family = "llama"', 'family = "qwen"', "distinct families"),
    ("[engine.llamacpp", "[engine.mystery", "unknown engine"),
    ('registered_by = ""', 'registered_by = "1"', "four-digit"),
])
def test_engines_config_refuses_bad_values(tmp_path, old, new, msg):
    assert ENGINES.count(old) >= 1
    with pytest.raises(ValueError, match=msg):
        load_engines_config(_write(tmp_path, "engines.toml", ENGINES.replace(old, new)))


def test_repo_configs_load():
    from prefix_mortality import REPO_ROOT
    seal = load_seal_config(REPO_ROOT / "config" / "seal.toml", REPO_ROOT)
    for root in seal.artifact_roots:
        assert root.path.is_dir(), f"{root.path} must exist in a fresh clone: the seal writer fails closed on it"
    controls = load_controls_config(REPO_ROOT / "config" / "controls.toml", REPO_ROOT)
    assert controls.registered_by == "", "the controls config is registered: update this test with the entry number"
    assert controls.corpus_dir.parent == REPO_ROOT / "corpus" / "live"
    engine = load_engines_config(REPO_ROOT / "config" / "engines.toml")["llamacpp"]
    assert engine.registered_by == "" and not engine.pinned
    assert {m.family for m in engine.models} == {"qwen", "llama"}
