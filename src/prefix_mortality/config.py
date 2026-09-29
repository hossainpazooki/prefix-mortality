"""TOML config -> frozen dataclasses. Seeds and thresholds live here, never in code.

Adapted from lag-ladder `src/lag_ladder/config.py` (UPSTREAM.md provenance): the seal loader is
verbatim; the pilot loader is dropped; `load_controls_config`, `load_m1_config` and
`load_engines_config` are new.
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


def _text(c: dict, key: str, name: str) -> str:
    v = c[key]
    if not isinstance(v, str) or not v:
        raise ValueError(f"{name} {key} must be a non-empty string, got {v!r}")
    return v


def _digest(c: dict, key: str, name: str, pattern: re.Pattern) -> str:
    v = str(c[key])
    if not pattern.fullmatch(v):
        raise ValueError(f"{name} {key} {v!r} is not a lowercase hex digest of the expected length")
    return v


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
    fixed these values; empty means UNREGISTERED and the driver refuses to run."""
    repetitions: int
    length_tolerance_tokens: int
    max_tokens: int
    temperature: float
    nonce_bytes: int
    seed: int
    request_timeout_seconds: float
    user_message: str
    corpus_dir: Path
    results_dir: Path
    registered_by: str
    config_path: Path


_CONTROLS_KEYS = ("repetitions", "length_tolerance_tokens", "max_tokens", "temperature", "nonce_bytes", "seed",
                  "request_timeout_seconds", "user_message", "corpus_dir", "results_dir", "registered_by")


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
        length_tolerance_tokens=_int(c, "length_tolerance_tokens", name, minimum=0),
        max_tokens=_int(c, "max_tokens", name, minimum=1),
        temperature=_number(c, "temperature", name),
        nonce_bytes=_int(c, "nonce_bytes", name, minimum=1),
        seed=int(c["seed"]),
        request_timeout_seconds=_number(c, "request_timeout_seconds", name),
        user_message=_text(c, "user_message", name),
        corpus_dir=root / c["corpus_dir"], results_dir=root / c["results_dir"],
        registered_by=_registered_by(c["registered_by"], name), config_path=path,
    )


# --- edit position (M1) --------------------------------------------------------------------------

M1_RULES = ("prefix", "threshold")
_M1_ID = re.compile(r"H-M1L[A-Za-z0-9]")


@dataclass(frozen=True)
class M1Hypothesis:
    id: str
    slots: int
    rule: str


@dataclass(frozen=True)
class M1Config:
    """Edit position. One list of sites, run once per hypothesis; a hypothesis is a server
    configuration and the rule that predicts reuse under it. Request parameters come from the
    controls config."""
    repetitions: int
    replacement: str
    system_fractions: tuple[float, ...]
    tool_indexes: tuple[int, ...]
    edit_user_message: bool
    similarity_threshold: float
    threshold_margin: float
    corpus_dir: Path
    results_dir: Path
    hypotheses: tuple[M1Hypothesis, ...]
    registered_by: str
    config_path: Path

    def hypothesis(self, hid: str) -> M1Hypothesis:
        for h in self.hypotheses:
            if h.id == hid:
                return h
        raise ValueError(f"{self.config_path.name} registers no hypothesis {hid!r}; "
                         f"known: {[h.id for h in self.hypotheses]}")


_M1_KEYS = ("repetitions", "replacement", "system_fractions", "tool_indexes", "edit_user_message",
            "similarity_threshold", "threshold_margin", "corpus_dir", "results_dir", "registered_by", "hypotheses")
_M1_HYPOTHESIS_KEYS = ("slots", "rule")


def _ascending(c: dict, key: str, name: str, kind: type, lo: float, hi: float) -> tuple:
    v = c[key]
    allowed = (int, float) if kind is float else (int,)
    ok = isinstance(v, list) and all(isinstance(x, allowed) and not isinstance(x, bool) and lo <= x <= hi
                                     for x in v)
    if not ok or any(b <= a for a, b in zip(v, v[1:])):
        raise ValueError(f"{name} {key} must be a list of {kind.__name__} in [{lo}, {hi}], strictly ascending, "
                         f"got {v!r}")
    return tuple(kind(x) for x in v)


def load_m1_config(path: Path, repo_root: Path) -> M1Config:
    path = Path(path)
    name = f"{path.name} [m1]"
    c = _read(path)["m1"]
    _require(c, _M1_KEYS, name)
    if not isinstance(c["edit_user_message"], bool):
        raise ValueError(f"{name} edit_user_message must be true or false")
    replacement = _text(c, "replacement", name)
    if not replacement.isalpha():
        raise ValueError(f"{name} replacement must be one word of letters, got {replacement!r}")
    threshold, margin = _number(c, "similarity_threshold", name), _number(c, "threshold_margin", name)
    if not 0 < threshold < 1:
        raise ValueError(f"{name} similarity_threshold must be between 0 and 1, got {threshold!r}")
    fractions = _ascending(c, "system_fractions", name, float, 0.0, 1.0)
    indexes = _ascending(c, "tool_indexes", name, int, 0, 10_000)
    if not (fractions or indexes or c["edit_user_message"]):
        raise ValueError(f"{name} names no site")
    hypotheses = []
    for hid, h in c["hypotheses"].items():
        hname = f"{name}.hypotheses.{hid}"
        if not _M1_ID.fullmatch(hid):
            raise ValueError(f"{hname}: an id is H-M1L and one letter or digit for the configuration")
        _require(h, _M1_HYPOTHESIS_KEYS, hname)
        if h["rule"] not in M1_RULES:
            raise ValueError(f"{hname} rule must be one of {M1_RULES}, got {h['rule']!r}")
        hypotheses.append(M1Hypothesis(id=hid, slots=_int(h, "slots", hname, minimum=1), rule=h["rule"]))
    if not hypotheses:
        raise ValueError(f"{name} registers no hypothesis")
    root = Path(repo_root)
    return M1Config(
        repetitions=_int(c, "repetitions", name, minimum=1), replacement=replacement,
        system_fractions=fractions, tool_indexes=indexes, edit_user_message=c["edit_user_message"],
        similarity_threshold=threshold, threshold_margin=margin,
        corpus_dir=root / c["corpus_dir"], results_dir=root / c["results_dir"],
        hypotheses=tuple(hypotheses), registered_by=_registered_by(c["registered_by"], name), config_path=path,
    )


# --- engines -------------------------------------------------------------------------------------

@dataclass(frozen=True)
class EngineModel:
    family: str
    hf_repo: str
    file: str
    sha256: str


@dataclass(frozen=True)
class EngineConfig:
    """One serving engine, pinned to a release, the commit it was built from and the download's
    digest. No server flag is configured: a run is at the server's defaults unless the entry that
    registers an experiment names an override."""
    name: str
    repo: str
    release: str
    commit: str
    download: str
    download_sha256: str
    models: tuple[EngineModel, ...]
    registered_by: str
    config_path: Path

    def model(self, family: str) -> EngineModel:
        for m in self.models:
            if m.family == family:
                return m
        raise ValueError(f"engine {self.name} has no model of family {family!r}; "
                         f"known: {[m.family for m in self.models]}")


_ENGINE_KEYS = ("repo", "release", "commit", "download", "download_sha256", "models", "registered_by")
_MODEL_KEYS = ("family", "hf_repo", "file", "sha256")


def load_engines_config(path: Path) -> dict[str, EngineConfig]:
    path = Path(path)
    engines = _read(path).get("engine") or {}
    if not engines:
        raise ValueError(f"{path.name} names no [engine.<name>]")
    out = {}
    for ename, c in engines.items():
        name = f"{path.name} [engine.{ename}]"
        _require(c, _ENGINE_KEYS, name)
        models = []
        for m in c["models"]:
            mname = f"{name}.models"
            _require(m, _MODEL_KEYS, mname)
            models.append(EngineModel(family=_text(m, "family", mname), hf_repo=_text(m, "hf_repo", mname),
                                      file=_text(m, "file", mname), sha256=_digest(m, "sha256", mname, _SHA256)))
        families = [m.family for m in models]
        if not models or len(set(families)) != len(families):
            raise ValueError(f"{name} needs at least one model and distinct families, got {families}")
        out[ename] = EngineConfig(
            name=ename, repo=_text(c, "repo", name), release=_text(c, "release", name),
            commit=_digest(c, "commit", name, _SHA40), download=_text(c, "download", name),
            download_sha256=_digest(c, "download_sha256", name, _SHA256), models=tuple(models),
            registered_by=_registered_by(c["registered_by"], name), config_path=path)
    return out
