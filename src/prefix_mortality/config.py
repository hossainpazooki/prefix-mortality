"""TOML config -> frozen dataclasses. Seeds and thresholds live here, never in code.

Adapted from lag-ladder `src/lag_ladder/config.py` (UPSTREAM.md provenance): the seal loader is
verbatim; the pilot loader is dropped; `load_controls_config` and `load_engines_config` are new.
"""
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArtifactRoot:
    path: Path
    pattern: str


@dataclass(frozen=True)
class SealConfig:
    predictions_dir: Path
    upstream_path: Path
    artifact_roots: tuple[ArtifactRoot, ...]


def _read(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _resolve(repo_root: Path, raw: str, upstream: Path | None = None) -> Path:
    if "${upstream}" in raw:
        if upstream is None:
            raise ValueError("${upstream} used before upstream_path was known")
        raw = raw.replace("${upstream}", upstream.as_posix())
        return Path(raw).resolve()
    return (repo_root / raw)


def load_seal_config(path: Path, repo_root: Path) -> SealConfig:
    d = _read(Path(path))
    repo_root = Path(repo_root)
    upstream = repo_root / d["upstream_path"]
    roots = []
    for r in d.get("artifact_roots", []):
        if "{pair}" not in r["pattern"]:
            raise ValueError(f"artifact root pattern {r['pattern']!r} has no {{pair}} placeholder; "
                             "a root that cannot be scoped to a pair would match everything or nothing")
        roots.append(ArtifactRoot(_resolve(repo_root, r["path"], upstream), r["pattern"]))
    if not roots:
        raise ValueError("seal config lists no artifact_roots; the writer would have nothing to refuse on")
    return SealConfig(predictions_dir=repo_root / d["predictions_dir"],
                      upstream_path=upstream, artifact_roots=tuple(roots))


# --- shared validators ---------------------------------------------------------------------------

_SHA40 = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_PENDING = re.compile(r"[A-Z0-9_]+_PENDING")


def _registered_by(raw, name: str) -> str:
    reg = str(raw)
    if reg and not (len(reg) == 4 and reg.isdigit()):
        raise ValueError(f"{name} registered_by must be a four-digit ledger entry or empty")
    return reg


def _int(c: dict, key: str, name: str, *, minimum: int) -> int:
    v = c[key]
    if isinstance(v, bool) or not isinstance(v, int) or v < minimum:
        raise ValueError(f"{name} {key} must be an int >= {minimum}, got {v!r}")
    return v


def _number(c: dict, key: str, name: str) -> float:
    v = c[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
        raise ValueError(f"{name} {key} must be a non-negative number, got {v!r}")
    return float(v)


def _require(c: dict, keys: tuple[str, ...], name: str) -> None:
    missing = [k for k in keys if k not in c]
    if missing:
        raise ValueError(f"{name} is missing {missing}")
    extra = sorted(set(c) - set(keys))
    if extra:
        raise ValueError(f"{name} has unknown keys {extra}; a key the loader does not read is a "
                         "setting nobody validates")


# --- controls ------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ControlsConfig:
    """Identity and scramble (ledger entry 0001). `registered_by` is the four-digit ledger entry that
    fixed these values; empty means UNREGISTERED and a gate must refuse to run."""
    repetitions: int
    settle_seconds: float
    length_tolerance_tokens: int
    max_retries: int
    retry_wait_seconds: float
    nonce_bytes: int
    seed: int
    corpus_dir: Path
    results_dir: Path
    registered_by: str
    config_path: Path


_CONTROLS_KEYS = ("repetitions", "settle_seconds", "length_tolerance_tokens", "max_retries",
                  "retry_wait_seconds", "nonce_bytes", "seed", "corpus_dir", "results_dir", "registered_by")


def load_controls_config(path: Path, repo_root: Path) -> ControlsConfig:
    path = Path(path)
    name = f"{path.name} [controls]"
    c = _read(path)["controls"]
    _require(c, _CONTROLS_KEYS, name)
    if isinstance(c["seed"], bool) or not isinstance(c["seed"], int):
        raise ValueError(f"{name} seed must be an int")
    root = Path(repo_root)
    return ControlsConfig(
        repetitions=_int(c, "repetitions", name, minimum=1),
        settle_seconds=_number(c, "settle_seconds", name),
        length_tolerance_tokens=_int(c, "length_tolerance_tokens", name, minimum=0),
        max_retries=_int(c, "max_retries", name, minimum=0),
        retry_wait_seconds=_number(c, "retry_wait_seconds", name),
        nonce_bytes=_int(c, "nonce_bytes", name, minimum=1),
        seed=int(c["seed"]), corpus_dir=root / c["corpus_dir"], results_dir=root / c["results_dir"],
        registered_by=_registered_by(c["registered_by"], name), config_path=path,
    )


# --- engines -------------------------------------------------------------------------------------

@dataclass(frozen=True)
class EngineModel:
    family: str
    hf_repo: str
    file: str
    sha256: str          # a 64-hex digest, or a *_PENDING placeholder the gate refuses by name

    @property
    def pinned(self) -> bool:
        return bool(_SHA256.fullmatch(self.sha256))


@dataclass(frozen=True)
class EngineConfig:
    """One serving engine. Every flag that changes what a cache death looks like is REQUIRED: a flag
    left to the server's default is a setting the record cannot state."""
    name: str
    repo: str
    commit: str          # a 40-hex sha, or a *_PENDING placeholder the gate refuses by name
    flags: dict
    models: tuple[EngineModel, ...]
    registered_by: str
    config_path: Path

    @property
    def pinned(self) -> bool:
        return bool(_SHA40.fullmatch(self.commit)) and all(m.pinned for m in self.models)


_ENGINE_KEYS = ("repo", "commit", "flags", "models", "registered_by")
_LLAMACPP_FLAGS = {"cache_prompt": bool, "cache_reuse": int, "cache_ram_mib": int, "ctx_size": int,
                   "parallel": int, "slot_prompt_similarity": float}
_FLAGS = {"llamacpp": _LLAMACPP_FLAGS}
_MODEL_KEYS = ("family", "hf_repo", "file", "sha256")


def _pin(raw, pattern: re.Pattern, what: str) -> str:
    s = str(raw)
    if not (pattern.fullmatch(s) or _PENDING.fullmatch(s)):
        raise ValueError(f"{what} {s!r} is neither a digest of the expected length nor a *_PENDING placeholder")
    return s


def load_engines_config(path: Path) -> dict[str, EngineConfig]:
    path = Path(path)
    engines = _read(path).get("engine") or {}
    if not engines:
        raise ValueError(f"{path.name} names no [engine.<name>]")
    out = {}
    for ename, c in engines.items():
        name = f"{path.name} [engine.{ename}]"
        if ename not in _FLAGS:
            raise ValueError(f"{name}: unknown engine; known engines are {sorted(_FLAGS)}")
        _require(c, _ENGINE_KEYS, name)
        want = _FLAGS[ename]
        _require(c["flags"], tuple(sorted(want)), f"{name}.flags")
        for k, typ in want.items():
            v = c["flags"][k]
            ok = (isinstance(v, bool) if typ is bool else
                  not isinstance(v, bool) and isinstance(v, (int, float) if typ is float else int))
            if not ok:
                raise ValueError(f"{name}.flags {k} must be {typ.__name__}, got {v!r}")
        models = []
        for m in c["models"]:
            _require(m, _MODEL_KEYS, f"{name}.models")
            models.append(EngineModel(family=str(m["family"]), hf_repo=str(m["hf_repo"]), file=str(m["file"]),
                                      sha256=_pin(m["sha256"], _SHA256, f"{name}.models sha256")))
        families = [m.family for m in models]
        if not models or len(set(families)) != len(families):
            raise ValueError(f"{name} needs at least one model and distinct families, got {families}")
        out[ename] = EngineConfig(name=ename, repo=str(c["repo"]),
                                  commit=_pin(c["commit"], _SHA40, f"{name} commit"),
                                  flags=dict(c["flags"]), models=tuple(models),
                                  registered_by=_registered_by(c["registered_by"], name), config_path=path)
    return out
