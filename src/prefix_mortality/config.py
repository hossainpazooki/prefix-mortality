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
_M1Q17_ID = re.compile(r"H-M1L[A-Za-z0-9]Q17")
_M1SM3_ID = re.compile(r"H-M1L[A-Za-z0-9]SM3")


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
    return _load_m1_like(path, repo_root, "m1", _M1_ID, "an id is H-M1L and one letter or digit for the configuration")


def load_m1q17_config(path: Path, repo_root: Path) -> M1Config:
    """config/m1q17.toml: the M1 instrument on the qwen17 family (config/l17.toml). Own file because
    the committed M1 records seal config/m1.toml by hash; own ids because the sealed verdicts stay
    sealed. Byte-parity of the sites with m1.toml is held by a test, not by this loader."""
    return _load_m1_like(path, repo_root, "m1q17", _M1Q17_ID,
                         "an id is H-M1L, one letter or digit for the configuration, then Q17 for the family")


def load_m1sm3_config(path: Path, repo_root: Path) -> M1Config:
    """config/m1sm3.toml: the M1 instrument on the smollm3 family (config/lsm3.toml), m1q17's shape
    and reasons. Byte-parity of the sites with m1.toml is held by a test, not by this loader."""
    return _load_m1_like(path, repo_root, "m1sm3", _M1SM3_ID,
                         "an id is H-M1L, one letter or digit for the configuration, then SM3 for the family")


def _load_m1_like(path: Path, repo_root: Path, table: str, id_re: re.Pattern, id_msg: str) -> M1Config:
    path = Path(path)
    name = f"{path.name} [{table}]"
    c = _read(path)[table]
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
        if not id_re.fullmatch(hid):
            raise ValueError(f"{hname}: {id_msg}")
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


# --- eviction by intervening requests (M7) -------------------------------------------------------

_M7_ID = re.compile(r"H-M7L[A-Za-z0-9]")


@dataclass(frozen=True)
class KVGeometry:
    """What sizes a cached prompt: the model file's layer count, KV heads, head width and KV value
    width in bytes. One token's state is n_layer x 2 x n_head_kv x head_dim x bytes_per_value."""
    n_layer: int
    n_head_kv: int
    head_dim: int
    bytes_per_value: int

    @property
    def bytes_per_token(self) -> int:
        return self.n_layer * 2 * self.n_head_kv * self.head_dim * self.bytes_per_value


@dataclass(frozen=True)
class M7Hypothesis:
    id: str
    slots: int


@dataclass(frozen=True)
class M7Config:
    """Eviction by intervening requests. One schedule of K values, run under one hypothesis per
    server configuration. Request parameters come from the controls config."""
    repetitions: int
    k_schedule: tuple[int, ...]
    cache_ram_mib: int
    kv_geometry: tuple[tuple[str, KVGeometry], ...]
    corpus_dir: Path
    results_dir: Path
    hypotheses: tuple[M7Hypothesis, ...]
    registered_by: str
    config_path: Path

    @property
    def cache_limit_bytes(self) -> int:
        return self.cache_ram_mib * 1024 * 1024

    def geometry(self, family: str) -> KVGeometry:
        for fam, g in self.kv_geometry:
            if fam == family:
                return g
        raise ValueError(f"{self.config_path.name} has no kv_geometry for family {family!r}; "
                         f"known: {[f for f, _ in self.kv_geometry]}")

    def bytes_per_token(self, family: str) -> int:
        return self.geometry(family).bytes_per_token

    def hypothesis(self, hid: str) -> M7Hypothesis:
        for h in self.hypotheses:
            if h.id == hid:
                return h
        raise ValueError(f"{self.config_path.name} registers no hypothesis {hid!r}; "
                         f"known: {[h.id for h in self.hypotheses]}")


_M7_KEYS = ("repetitions", "k_schedule", "cache_ram_mib", "kv_geometry", "corpus_dir", "results_dir",
            "registered_by", "hypotheses")
_M7_GEOMETRY_KEYS = ("n_layer", "n_head_kv", "head_dim", "bytes_per_value")
_M7_HYPOTHESIS_KEYS = ("slots",)


def load_m7_config(path: Path, repo_root: Path) -> M7Config:
    path = Path(path)
    name = f"{path.name} [m7]"
    c = _read(path)["m7"]
    _require(c, _M7_KEYS, name)
    schedule = _ascending(c, "k_schedule", name, int, 0, 10_000)
    if not schedule:
        raise ValueError(f"{name} k_schedule names no K")
    geometry = []
    for family, g in (c["kv_geometry"] or {}).items():
        gname = f"{name}.kv_geometry.{family}"
        _require(g, _M7_GEOMETRY_KEYS, gname)
        geometry.append((family, KVGeometry(*(_int(g, k, gname, minimum=1) for k in _M7_GEOMETRY_KEYS))))
    if not geometry:
        raise ValueError(f"{name} has no kv_geometry; nothing sizes a cached prompt")
    hypotheses = []
    for hid, h in c["hypotheses"].items():
        hname = f"{name}.hypotheses.{hid}"
        if not _M7_ID.fullmatch(hid):
            raise ValueError(f"{hname}: an id is H-M7L and one letter or digit for the configuration")
        _require(h, _M7_HYPOTHESIS_KEYS, hname)
        hypotheses.append(M7Hypothesis(id=hid, slots=_int(h, "slots", hname, minimum=1)))
    if not hypotheses:
        raise ValueError(f"{name} registers no hypothesis")
    root = Path(repo_root)
    return M7Config(
        repetitions=_int(c, "repetitions", name, minimum=1), k_schedule=schedule,
        cache_ram_mib=_int(c, "cache_ram_mib", name, minimum=1), kv_geometry=tuple(geometry),
        corpus_dir=root / c["corpus_dir"], results_dir=root / c["results_dir"],
        hypotheses=tuple(hypotheses), registered_by=_registered_by(c["registered_by"], name), config_path=path,
    )


# --- shared: hypotheses with a slot count and a reuse rule --------------------------------------

@dataclass(frozen=True)
class RuleHypothesis:
    id: str
    slots: int
    rule: str


_RULE_HYPOTHESIS_KEYS = ("slots", "rule")


def _rule_hypotheses(c: dict, name: str, pattern: re.Pattern, prefix: str) -> tuple[RuleHypothesis, ...]:
    out = []
    for hid, h in (c.get("hypotheses") or {}).items():
        hname = f"{name}.hypotheses.{hid}"
        if not pattern.fullmatch(hid):
            raise ValueError(f"{hname}: an id is {prefix} and one letter or digit for the configuration")
        _require(h, _RULE_HYPOTHESIS_KEYS, hname)
        if h["rule"] not in M1_RULES:
            raise ValueError(f"{hname} rule must be one of {M1_RULES}, got {h['rule']!r}")
        out.append(RuleHypothesis(id=hid, slots=_int(h, "slots", hname, minimum=1), rule=h["rule"]))
    if not out:
        raise ValueError(f"{name} registers no hypothesis")
    return tuple(out)


def _find(items, key: str, what: str, config_name: str, attr: str = "id"):
    for it in items:
        if getattr(it, attr) == key:
            return it
    raise ValueError(f"{config_name} registers no {what} {key!r}; known: {[getattr(i, attr) for i in items]}")


# --- serialization drift (M2) --------------------------------------------------------------------

_M2_ID = re.compile(r"H-M2L[A-Za-z0-9]")
_M2_CHANGE_IDS = ("S1", "S2", "S3", "S4", "S5", "S6")      # the ids serialize.CHANGES implements
M2_READINGS = ("identical", "differs")


@dataclass(frozen=True)
class M2Change:
    id: str
    reading: str


@dataclass(frozen=True)
class M2Config:
    """Serialization drift: a list of re-serializations of the tools, each with the reading of what
    the render will do, run under one hypothesis per server configuration."""
    repetitions: int
    changes: tuple[M2Change, ...]
    corpus_dir: Path
    results_dir: Path
    hypotheses: tuple[RuleHypothesis, ...]
    registered_by: str
    config_path: Path

    def hypothesis(self, hid: str) -> RuleHypothesis:
        return _find(self.hypotheses, hid, "hypothesis", self.config_path.name)

    def change(self, cid: str) -> M2Change:
        return _find(self.changes, cid, "change", self.config_path.name)


_M2_KEYS = ("repetitions", "corpus_dir", "results_dir", "registered_by", "changes", "hypotheses")


def load_m2_config(path: Path, repo_root: Path) -> M2Config:
    path = Path(path)
    name = f"{path.name} [m2]"
    c = _read(path)["m2"]
    _require(c, _M2_KEYS, name)
    changes = []
    for cid, ch in (c["changes"] or {}).items():
        cname = f"{name}.changes.{cid}"
        if cid not in _M2_CHANGE_IDS:
            raise ValueError(f"{cname}: {cid!r} is not a registered change id; known: {list(_M2_CHANGE_IDS)}")
        _require(ch, ("reading",), cname)
        if ch["reading"] not in M2_READINGS:
            raise ValueError(f"{cname} reading must be one of {M2_READINGS}, got {ch['reading']!r}")
        changes.append(M2Change(id=cid, reading=ch["reading"]))
    if not changes:
        raise ValueError(f"{name} registers no change")
    root = Path(repo_root)
    return M2Config(repetitions=_int(c, "repetitions", name, minimum=1), changes=tuple(changes),
                    corpus_dir=root / c["corpus_dir"], results_dir=root / c["results_dir"],
                    hypotheses=_rule_hypotheses(c, name, _M2_ID, "H-M2L"),
                    registered_by=_registered_by(c["registered_by"], name), config_path=path)


# --- templating (M3) -----------------------------------------------------------------------------

_M3_ID = re.compile(r"H-M3L[A-Za-z0-9]")
_M3_CHANGE_ID = re.compile(r"T[0-9]")


@dataclass(frozen=True)
class M3Change:
    id: str
    key: str
    value: str | bool


@dataclass(frozen=True)
class M3Config:
    """Templating: chat-template arguments on every request, and a list of single-argument changes,
    run under one hypothesis per server configuration."""
    repetitions: int
    base_kwargs: dict
    changes: tuple[M3Change, ...]
    similarity_threshold: float
    threshold_margin: float
    corpus_dir: Path
    results_dir: Path
    hypotheses: tuple[RuleHypothesis, ...]
    registered_by: str
    config_path: Path

    def hypothesis(self, hid: str) -> RuleHypothesis:
        return _find(self.hypotheses, hid, "hypothesis", self.config_path.name)

    def change(self, cid: str) -> M3Change:
        return _find(self.changes, cid, "change", self.config_path.name)


_M3_KEYS = ("repetitions", "similarity_threshold", "threshold_margin", "corpus_dir", "results_dir", "registered_by",
            "base_kwargs", "changes", "hypotheses")


def _kwarg_value(v, where: str):
    if isinstance(v, bool) or isinstance(v, str):
        return v
    raise ValueError(f"{where} must be a string or a boolean, got {v!r}")


def load_m3_config(path: Path, repo_root: Path) -> M3Config:
    path = Path(path)
    name = f"{path.name} [m3]"
    c = _read(path)["m3"]
    _require(c, _M3_KEYS, name)
    threshold, margin = _number(c, "similarity_threshold", name), _number(c, "threshold_margin", name)
    if not 0 < threshold < 1:
        raise ValueError(f"{name} similarity_threshold must be between 0 and 1, got {threshold!r}")
    base = {k: _kwarg_value(v, f"{name}.base_kwargs.{k}") for k, v in (c["base_kwargs"] or {}).items()}
    if not base:
        raise ValueError(f"{name} base_kwargs is empty; a change needs a base value to replace")
    changes = []
    for cid, ch in (c["changes"] or {}).items():
        cname = f"{name}.changes.{cid}"
        if not _M3_CHANGE_ID.fullmatch(cid):
            raise ValueError(f"{cname}: {cid!r} is not a registered change id (T and one digit)")
        _require(ch, ("key", "value"), cname)
        key = _text(ch, "key", cname)
        if key not in base:
            raise ValueError(f"{cname} key {key!r} is not in base_kwargs; the change would add an argument, not change one")
        value = _kwarg_value(ch["value"], f"{cname}.value")
        if value == base[key]:
            raise ValueError(f"{cname} value equals the base value {base[key]!r}; the change would change nothing")
        changes.append(M3Change(id=cid, key=key, value=value))
    if not changes:
        raise ValueError(f"{name} registers no change")
    root = Path(repo_root)
    return M3Config(repetitions=_int(c, "repetitions", name, minimum=1), base_kwargs=base, changes=tuple(changes),
                    similarity_threshold=threshold, threshold_margin=margin,
                    corpus_dir=root / c["corpus_dir"], results_dir=root / c["results_dir"],
                    hypotheses=_rule_hypotheses(c, name, _M3_ID, "H-M3L"),
                    registered_by=_registered_by(c["registered_by"], name), config_path=path)


# --- idle expiry (M4) ----------------------------------------------------------------------------

_M4_ID = re.compile(r"H-M4L[A-Za-z0-9]")
_M4_KEYS = ("sleep_margin_seconds", "corpus_dir", "results_dir", "registered_by", "hypotheses")
_M4_HYPOTHESIS_KEYS = ("slots", "sleep_idle_seconds", "gaps", "repetitions")


@dataclass(frozen=True)
class M4Hypothesis:
    """One server configuration: the slots it must report, its idle timer in seconds (-1 for none,
    the server's default), the gaps to wait before the resend, and how many trials per gap."""
    id: str
    slots: int
    sleep_idle_seconds: int
    gaps: tuple[int, ...]
    repetitions: int

    @property
    def sleeps(self) -> bool:
        return self.sleep_idle_seconds >= 1


@dataclass(frozen=True)
class M4Config:
    """Idle expiry. Request parameters come from the controls config."""
    sleep_margin_seconds: int
    corpus_dir: Path
    results_dir: Path
    hypotheses: tuple[M4Hypothesis, ...]
    registered_by: str
    config_path: Path

    def hypothesis(self, hid: str) -> M4Hypothesis:
        return _find(self.hypotheses, hid, "hypothesis", self.config_path.name)


def load_m4_config(path: Path, repo_root: Path) -> M4Config:
    path = Path(path)
    name = f"{path.name} [m4]"
    c = _read(path)["m4"]
    _require(c, _M4_KEYS, name)
    margin = _int(c, "sleep_margin_seconds", name, minimum=1)
    hypotheses = []
    for hid, h in c["hypotheses"].items():
        hname = f"{name}.hypotheses.{hid}"
        if not _M4_ID.fullmatch(hid):
            raise ValueError(f"{hname}: an id is H-M4L and one letter or digit for the configuration")
        _require(h, _M4_HYPOTHESIS_KEYS, hname)
        s = h["sleep_idle_seconds"]
        if isinstance(s, bool) or not isinstance(s, int) or s == 0 or s < -1:
            raise ValueError(f"{hname} sleep_idle_seconds must be -1 (no timer) or an int >= 1; the server "
                             f"refuses 0 and anything below -1; got {s!r}")
        gaps = _ascending(h, "gaps", hname, int, 0, 86_400)
        if not gaps:
            raise ValueError(f"{hname} gaps names no gap")
        if s >= 1:
            near = [g for g in gaps if abs(g - s) < margin]
            if near:
                raise ValueError(f"{hname}: gaps {near} are within {margin} s of the sleep threshold {s}; the "
                                 "server checks idleness once a second, so such a gap predicts nothing")
        hypotheses.append(M4Hypothesis(id=hid, slots=_int(h, "slots", hname, minimum=1), sleep_idle_seconds=s,
                                       gaps=gaps, repetitions=_int(h, "repetitions", hname, minimum=1)))
    if not hypotheses:
        raise ValueError(f"{name} registers no hypothesis")
    root = Path(repo_root)
    return M4Config(sleep_margin_seconds=margin, corpus_dir=root / c["corpus_dir"],
                    results_dir=root / c["results_dir"], hypotheses=tuple(hypotheses),
                    registered_by=_registered_by(c["registered_by"], name), config_path=path)


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


# --- later model families on the pinned engines (config/l17.toml, lsm3.toml, vsm3.toml) ---------

# family -> (its llama.cpp family file, its vLLM family file). None where the lane's main config
# (engines.toml, vllm.toml) pins the family itself. The committed records seal those two files by
# hash, so every later family lives in files of its own; a record of such a family hashes its file
# under the file's stem.
FAMILY_FILES: dict[str, tuple[str | None, str | None]] = {
    "qwen17": ("l17.toml", None),          # entry 0028; on vLLM the family is config/vllm.toml's own
    "smollm3": ("lsm3.toml", "vsm3.toml"),  # design of 2026-10-23; unregistered until an entry names it
}


@dataclass(frozen=True)
class ChatTemplatePin:
    """A chat template served in place of the model file's embedded one (`--chat-template-file`),
    pinned to a repository revision and a digest. Present only when the registering entry names the
    override."""
    hf_repo: str
    revision: str
    file: str
    sha256: str


@dataclass(frozen=True)
class L17Config:
    """One more model family served by the engine pinned in config/engines.toml, in its own file
    because the committed records seal engines.toml by hash. A run under this family gates on this
    file's registration and hashes it into its records. The name is the first such file's; the
    loader reads any family file whose table is the file's stem."""
    model: EngineModel
    registered_by: str
    config_path: Path
    chat_template: ChatTemplatePin | None = None


_L17_KEYS = ("registered_by", "model")
_TEMPLATE_KEYS = ("hf_repo", "revision", "file", "sha256")


def load_l17_config(path: Path) -> L17Config:
    path = Path(path)
    table = path.stem
    name = f"{path.name} [{table}]"
    c = _read(path)[table]
    _require(c, _L17_KEYS + (("chat_template",) if "chat_template" in c else ()), name)   # the pin is optional
    m, mname = c["model"], f"{path.name} [{table}.model]"
    _require(m, _MODEL_KEYS, mname)
    model = EngineModel(family=_text(m, "family", mname), hf_repo=_text(m, "hf_repo", mname),
                        file=_text(m, "file", mname), sha256=_digest(m, "sha256", mname, _SHA256))
    template = None
    if "chat_template" in c:
        t, tname = c["chat_template"], f"{path.name} [{table}.chat_template]"
        _require(t, _TEMPLATE_KEYS, tname)
        template = ChatTemplatePin(hf_repo=_text(t, "hf_repo", tname), revision=_text(t, "revision", tname),
                                   file=_text(t, "file", tname), sha256=_digest(t, "sha256", tname, _SHA256))
    return L17Config(model=model, registered_by=_registered_by(c["registered_by"], name), config_path=path,
                     chat_template=template)


load_family_config = load_l17_config


# --- vLLM (the V instrument) -----------------------------------------------------------------------

@dataclass(frozen=True)
class VllmModelFile:
    name: str
    sha256: str


@dataclass(frozen=True)
class VllmModel:
    family: str
    hf_repo: str
    files: tuple[VllmModelFile, ...]
    revision: str = ""      # the repository revision the files were taken from; "" where none was pinned


@dataclass(frozen=True)
class VllmConfig:
    """vLLM pinned to a commit and built from source (no release artifact exists for this platform).
    Lives in its own file: every committed llama.cpp record hashes config/engines.toml, so that file
    never changes. The server does not report its block size; a run's script passes one of the
    registered block_sizes and the records read it back only through the block arithmetic."""
    repo: str
    commit: str
    version: str
    served_model_name: str
    dtype: str
    max_model_len: int
    kvcache_space_gib: int
    block_sizes: tuple[int, ...]
    corpus_dir: Path
    results_dir: Path
    models: tuple[VllmModel, ...]
    registered_by: str
    config_path: Path

    def model(self, family: str) -> VllmModel:
        return _find(self.models, family, "model family", self.config_path.name, attr="family")


_VLLM_KEYS = ("repo", "commit", "version", "served_model_name", "dtype", "max_model_len",
              "kvcache_space_gib", "block_sizes", "corpus_dir", "results_dir", "registered_by", "models")
_VLLM_MODEL_KEYS = ("family", "hf_repo", "files")
_VLLM_FILE_KEYS = ("name", "sha256")


def _vllm_model(m: dict, mname: str) -> VllmModel:
    _require(m, _VLLM_MODEL_KEYS + (("revision",) if "revision" in m else ()), mname)   # revision is optional
    files = []
    for f in m["files"]:
        _require(f, _VLLM_FILE_KEYS, f"{mname}.files")
        files.append(VllmModelFile(name=_text(f, "name", mname), sha256=_digest(f, "sha256", mname, _SHA256)))
    if not files:
        raise ValueError(f"{mname} pins no file; nothing gates the local model")
    revision = _text(m, "revision", mname) if "revision" in m else ""
    return VllmModel(family=_text(m, "family", mname), hf_repo=_text(m, "hf_repo", mname), files=tuple(files),
                     revision=revision)


def load_vllm_config(path: Path, repo_root: Path) -> VllmConfig:
    path = Path(path)
    name = f"{path.name} [vllm]"
    c = _read(path)["vllm"]
    _require(c, _VLLM_KEYS, name)
    blocks = _ascending(c, "block_sizes", name, int, 1, 8192)
    if not blocks:
        raise ValueError(f"{name} block_sizes names no block size")
    models = []
    for m in c["models"]:
        mname = f"{name}.models"
        models.append(_vllm_model(m, mname))
    families = [m.family for m in models]
    if not models or len(set(families)) != len(families):
        raise ValueError(f"{name} needs at least one model and distinct families, got {families}")
    version = _text(c, "version", name)
    commit = _digest(c, "commit", name, _SHA40)
    if commit[:7] not in version:
        raise ValueError(f"{name} version {version!r} does not carry the commit {commit[:7]}; "
                         "the version gate would be vacuous")
    root = Path(repo_root)
    return VllmConfig(
        repo=_text(c, "repo", name), commit=commit, version=version,
        served_model_name=_text(c, "served_model_name", name), dtype=_text(c, "dtype", name),
        max_model_len=_int(c, "max_model_len", name, minimum=1),
        kvcache_space_gib=_int(c, "kvcache_space_gib", name, minimum=1), block_sizes=blocks,
        corpus_dir=root / c["corpus_dir"], results_dir=root / c["results_dir"], models=tuple(models),
        registered_by=_registered_by(c["registered_by"], name), config_path=path)


@dataclass(frozen=True)
class VFamilyConfig:
    """One more model family served by the vLLM pinned in config/vllm.toml, in its own file because
    the committed V records seal vllm.toml by hash (the l17.toml pattern on this lane). Carries the
    served model name and every pinned file; engine, dtype, context, KV space and block sizes stay
    vllm.toml's."""
    model: VllmModel
    served_model_name: str
    registered_by: str
    config_path: Path


_VFAMILY_KEYS = ("registered_by", "served_model_name", "model")


def load_vfamily_config(path: Path) -> VFamilyConfig:
    path = Path(path)
    table = path.stem
    name = f"{path.name} [{table}]"
    c = _read(path)[table]
    _require(c, _VFAMILY_KEYS, name)
    model = _vllm_model(c["model"], f"{path.name} [{table}.model]")
    return VFamilyConfig(model=model, served_model_name=_text(c, "served_model_name", name),
                         registered_by=_registered_by(c["registered_by"], name), config_path=path)


# --- edit position on vLLM (M1V) ------------------------------------------------------------------

_VM1_ID = re.compile(r"H-M1V[A-Za-z0-9]+")


@dataclass(frozen=True)
class Vm1Hypothesis:
    id: str
    block_size: int


@dataclass(frozen=True)
class Vm1Config:
    """Edit position on the V instrument. One list of sites, run once per hypothesis; a hypothesis
    is a server block size. Request parameters come from the controls config; engine, model and the
    registered block sizes from the vllm config, against which the driver gates each hypothesis."""
    repetitions: int
    replacement: str
    system_fractions: tuple[float, ...]
    tool_indexes: tuple[int, ...]
    edit_user_message: bool
    corpus_dir: Path
    results_dir: Path
    hypotheses: tuple[Vm1Hypothesis, ...]
    registered_by: str
    config_path: Path

    def hypothesis(self, hid: str) -> Vm1Hypothesis:
        for h in self.hypotheses:
            if h.id == hid:
                return h
        raise ValueError(f"{self.config_path.name} registers no hypothesis {hid!r}; "
                         f"known: {[h.id for h in self.hypotheses]}")


_VM1_KEYS = ("repetitions", "replacement", "system_fractions", "tool_indexes", "edit_user_message",
             "corpus_dir", "results_dir", "registered_by", "hypotheses")
_VM1_HYPOTHESIS_KEYS = ("block_size",)


def load_vm1_config(path: Path, repo_root: Path) -> Vm1Config:
    """config/vm1.toml, or a later family's own copy (config/vm1sm3.toml: the committed vm1 records
    seal vm1.toml by hash). The table is the file's stem; the ids carry the family after the block."""
    path = Path(path)
    table = path.stem
    name = f"{path.name} [{table}]"
    c = _read(path)[table]
    _require(c, _VM1_KEYS, name)
    if not isinstance(c["edit_user_message"], bool):
        raise ValueError(f"{name} edit_user_message must be true or false")
    replacement = _text(c, "replacement", name)
    if not replacement.isalpha():
        raise ValueError(f"{name} replacement must be one word of letters, got {replacement!r}")
    fractions = _ascending(c, "system_fractions", name, float, 0.0, 1.0)
    indexes = _ascending(c, "tool_indexes", name, int, 0, 10_000)
    if not (fractions or indexes or c["edit_user_message"]):
        raise ValueError(f"{name} names no site")
    hypotheses = []
    for hid, h in c["hypotheses"].items():
        hname = f"{name}.hypotheses.{hid}"
        if not _VM1_ID.fullmatch(hid):
            raise ValueError(f"{hname}: an id is H-M1V and the block size it runs under")
        _require(h, _VM1_HYPOTHESIS_KEYS, hname)
        hypotheses.append(Vm1Hypothesis(id=hid, block_size=_int(h, "block_size", hname, minimum=1)))
    blocks = [h.block_size for h in hypotheses]
    if not hypotheses or len(set(blocks)) != len(blocks):
        raise ValueError(f"{name} needs at least one hypothesis and distinct block sizes, got {blocks}")
    root = Path(repo_root)
    return Vm1Config(
        repetitions=_int(c, "repetitions", name, minimum=1), replacement=replacement,
        system_fractions=fractions, tool_indexes=indexes, edit_user_message=c["edit_user_message"],
        corpus_dir=root / c["corpus_dir"], results_dir=root / c["results_dir"],
        hypotheses=tuple(hypotheses), registered_by=_registered_by(c["registered_by"], name), config_path=path,
    )


# --- templating and serialization drift on V (config/vm3.toml, config/vm2.toml) -------------------

_VM2_ID = re.compile(r"H-M2V[A-Za-z0-9]+")
_VM3_ID = re.compile(r"H-M3V[A-Za-z0-9]+")
_VM2_ARMS = ("keyorder", "properties")
_VM3_ARMS = ("thinking-off", "thinking-on")


@dataclass(frozen=True)
class VmArmConfig:
    """A paired-request experiment on the V instrument: a base request, then one variant per arm.
    A hypothesis is a server block size, as in Vm1Config; the arms name the variant constructions,
    which live in the driver and are fixed by the registering entry."""
    experiment: str
    repetitions: int
    arms: tuple[str, ...]
    corpus_dir: Path
    results_dir: Path
    hypotheses: tuple[Vm1Hypothesis, ...]
    registered_by: str
    config_path: Path

    def hypothesis(self, hid: str) -> Vm1Hypothesis:
        for h in self.hypotheses:
            if h.id == hid:
                return h
        raise ValueError(f"{self.config_path.name} registers no hypothesis {hid!r}; "
                         f"known: {[h.id for h in self.hypotheses]}")


_VMARM_KEYS = ("repetitions", "arms", "corpus_dir", "results_dir", "registered_by", "hypotheses")


def _load_vmarm(path: Path, repo_root: Path, table: str, id_re: re.Pattern, id_msg: str,
                allowed_arms: tuple[str, ...]) -> VmArmConfig:
    path = Path(path)
    name = f"{path.name} [{table}]"
    c = _read(path)[table]
    _require(c, _VMARM_KEYS, name)
    arms = c["arms"]
    if (not isinstance(arms, list) or not arms or len(set(arms)) != len(arms)
            or any(a not in allowed_arms for a in arms)):
        raise ValueError(f"{name} arms must be distinct names from {list(allowed_arms)}, got {arms!r}")
    hypotheses = []
    for hid, h in c["hypotheses"].items():
        hname = f"{name}.hypotheses.{hid}"
        if not id_re.fullmatch(hid):
            raise ValueError(f"{hname}: {id_msg}")
        _require(h, _VM1_HYPOTHESIS_KEYS, hname)
        hypotheses.append(Vm1Hypothesis(id=hid, block_size=_int(h, "block_size", hname, minimum=1)))
    blocks = [h.block_size for h in hypotheses]
    if not hypotheses or len(set(blocks)) != len(blocks):
        raise ValueError(f"{name} needs at least one hypothesis and distinct block sizes, got {blocks}")
    root = Path(repo_root)
    return VmArmConfig(
        experiment=table, repetitions=_int(c, "repetitions", name, minimum=1), arms=tuple(arms),
        corpus_dir=root / c["corpus_dir"], results_dir=root / c["results_dir"],
        hypotheses=tuple(hypotheses), registered_by=_registered_by(c["registered_by"], name), config_path=path,
    )


def load_vm2_config(path: Path, repo_root: Path) -> VmArmConfig:
    return _load_vmarm(path, repo_root, "vm2", _VM2_ID,
                       "an id is H-M2V and the block size it runs under", _VM2_ARMS)


def load_vm3_config(path: Path, repo_root: Path) -> VmArmConfig:
    return _load_vmarm(path, repo_root, "vm3", _VM3_ID,
                       "an id is H-M3V and the block size it runs under", _VM3_ARMS)


# --- lifespan on recorded runs (M8) ----------------------------------------------------------------

_M8_ID = re.compile(r"H-M8L[A-Za-z0-9]")
_M8_KEYS = ("recorded_dir", "similarity_threshold", "cache_ram_mib", "kv_geometry", "template_kwargs",
            "corpus_dir", "results_dir", "registered_by", "hypotheses")
_M8_HYPOTHESIS_KEYS = ("slots", "interleave")


@dataclass(frozen=True)
class M8Hypothesis:
    """One server configuration: the slots it must report and the values of C (conversations replayed
    in round robin; 1 = one after another) a run under it may use."""
    id: str
    slots: int
    interleave: tuple[int, ...]


@dataclass(frozen=True)
class M8Config:
    """Lifespan on recorded runs. Request parameters come from the controls config; the prediction is
    the pinned server's slot and prompt-cache policy (slotsim) under these constants."""
    recorded_dir: Path
    similarity_threshold: float
    cache_ram_mib: int
    kv_geometry: tuple[tuple[str, KVGeometry], ...]
    template_kwargs: tuple[tuple[str, tuple[tuple[str, object], ...]], ...]
    corpus_dir: Path
    results_dir: Path
    hypotheses: tuple[M8Hypothesis, ...]
    registered_by: str
    config_path: Path

    @property
    def cache_limit_bytes(self) -> int:
        return self.cache_ram_mib * 1024 * 1024

    def geometry(self, family: str) -> KVGeometry:
        for fam, g in self.kv_geometry:
            if fam == family:
                return g
        raise ValueError(f"{self.config_path.name} has no kv_geometry for family {family!r}; "
                         f"known: {[f for f, _ in self.kv_geometry]}")

    def bytes_per_token(self, family: str) -> int:
        return self.geometry(family).bytes_per_token

    def kwargs(self, family: str) -> dict | None:
        """The family's chat-template arguments, or None when its table is empty."""
        for fam, kw in self.template_kwargs:
            if fam == family:
                return dict(kw) or None
        raise ValueError(f"{self.config_path.name} has no template_kwargs table for family {family!r}; "
                         f"known: {[f for f, _ in self.template_kwargs]}")

    def hypothesis(self, hid: str) -> M8Hypothesis:
        return _find(self.hypotheses, hid, "hypothesis", self.config_path.name)


def _geometries(c: dict, name: str) -> tuple[tuple[str, KVGeometry], ...]:
    geometry = []
    for family, g in (c["kv_geometry"] or {}).items():
        gname = f"{name}.kv_geometry.{family}"
        _require(g, _M7_GEOMETRY_KEYS, gname)
        geometry.append((family, KVGeometry(*(_int(g, k, gname, minimum=1) for k in _M7_GEOMETRY_KEYS))))
    if not geometry:
        raise ValueError(f"{name} has no kv_geometry; nothing sizes a cached prompt")
    return tuple(geometry)


def _template_kwargs(c: dict, name: str) -> tuple[tuple[str, tuple[tuple[str, object], ...]], ...]:
    out = []
    for family, kw in (c["template_kwargs"] or {}).items():
        if not isinstance(kw, dict):
            raise ValueError(f"{name}.template_kwargs.{family} must be a table")
        for k, v in kw.items():
            if not isinstance(v, (bool, int, float, str)):
                raise ValueError(f"{name}.template_kwargs.{family}.{k} must be a scalar, got {type(v).__name__}")
        out.append((family, tuple(kw.items())))
    if not out:
        raise ValueError(f"{name} has no template_kwargs table; one per family, empty when the template takes none")
    return tuple(out)


def load_m8_config(path: Path, repo_root: Path) -> M8Config:
    path = Path(path)
    name = f"{path.name} [m8]"
    c = _read(path)["m8"]
    _require(c, _M8_KEYS, name)
    threshold = _number(c, "similarity_threshold", name)
    if not 0 < threshold < 1:
        raise ValueError(f"{name} similarity_threshold must be between 0 and 1, got {threshold!r}")
    hypotheses = []
    for hid, h in c["hypotheses"].items():
        hname = f"{name}.hypotheses.{hid}"
        if not _M8_ID.fullmatch(hid):
            raise ValueError(f"{hname}: an id is H-M8L and one letter or digit for the configuration")
        _require(h, _M8_HYPOTHESIS_KEYS, hname)
        interleave = _ascending(h, "interleave", hname, int, 1, 1000)
        if not interleave:
            raise ValueError(f"{hname} interleave names no C")
        hypotheses.append(M8Hypothesis(id=hid, slots=_int(h, "slots", hname, minimum=1), interleave=interleave))
    if not hypotheses:
        raise ValueError(f"{name} registers no hypothesis")
    root = Path(repo_root)
    return M8Config(
        recorded_dir=root / c["recorded_dir"], similarity_threshold=threshold,
        cache_ram_mib=_int(c, "cache_ram_mib", name, minimum=1), kv_geometry=_geometries(c, name),
        template_kwargs=_template_kwargs(c, name), corpus_dir=root / c["corpus_dir"],
        results_dir=root / c["results_dir"], hypotheses=tuple(hypotheses),
        registered_by=_registered_by(c["registered_by"], name), config_path=path,
    )


# --- rebuild (M5) ---------------------------------------------------------------------------------

_M5_ID = re.compile(r"H-M5L[A-Za-z0-9]")
_M5_KEYS = ("recorded_dir", "conversations", "arms", "summary", "similarity_threshold", "threshold_margin",
            "cache_reuse_n", "template_kwargs", "corpus_dir", "results_dir", "registered_by", "hypotheses")
_M5_ARMS = ("trim", "summary")
M5_RULES = ("prefix", "threshold", "walk")


@dataclass(frozen=True)
class M5Config:
    """Rebuild: a recorded conversation compacted at its midpoint. Request parameters come from the
    controls config; the rules are M1's two plus the --cache-reuse walk (slotsim)."""
    recorded_dir: Path
    conversations: int
    arms: tuple[str, ...]
    summary: str
    similarity_threshold: float
    threshold_margin: float
    cache_reuse_n: int
    template_kwargs: tuple[tuple[str, tuple[tuple[str, object], ...]], ...]
    corpus_dir: Path
    results_dir: Path
    hypotheses: tuple[RuleHypothesis, ...]
    registered_by: str
    config_path: Path

    def kwargs(self, family: str) -> dict | None:
        for fam, kw in self.template_kwargs:
            if fam == family:
                return dict(kw) or None
        raise ValueError(f"{self.config_path.name} has no template_kwargs table for family {family!r}; "
                         f"known: {[f for f, _ in self.template_kwargs]}")

    def hypothesis(self, hid: str) -> RuleHypothesis:
        return _find(self.hypotheses, hid, "hypothesis", self.config_path.name)


def load_m5_config(path: Path, repo_root: Path) -> M5Config:
    path = Path(path)
    name = f"{path.name} [m5]"
    c = _read(path)["m5"]
    _require(c, _M5_KEYS, name)
    arms = tuple(c["arms"])
    if not arms or len(set(arms)) != len(arms) or any(a not in _M5_ARMS for a in arms):
        raise ValueError(f"{name} arms must be distinct names from {_M5_ARMS}, got {c['arms']!r}")
    if not isinstance(c["summary"], str) or not c["summary"].strip():
        raise ValueError(f"{name} summary must be a non-empty string")
    threshold, margin = _number(c, "similarity_threshold", name), _number(c, "threshold_margin", name)
    if not 0 < threshold < 1:
        raise ValueError(f"{name} similarity_threshold must be between 0 and 1, got {threshold!r}")
    if not 0 < margin < threshold:
        raise ValueError(f"{name} threshold_margin must be between 0 and the threshold, got {margin!r}")
    hypotheses = []
    for hid, h in (c.get("hypotheses") or {}).items():
        hname = f"{name}.hypotheses.{hid}"
        if not _M5_ID.fullmatch(hid):
            raise ValueError(f"{hname}: an id is H-M5L and one letter or digit for the configuration")
        _require(h, _RULE_HYPOTHESIS_KEYS, hname)
        if h["rule"] not in M5_RULES:
            raise ValueError(f"{hname} rule must be one of {M5_RULES}, got {h['rule']!r}")
        hypotheses.append(RuleHypothesis(id=hid, slots=_int(h, "slots", hname, minimum=1), rule=h["rule"]))
    if not hypotheses:
        raise ValueError(f"{name} registers no hypothesis")
    root = Path(repo_root)
    return M5Config(
        recorded_dir=root / c["recorded_dir"], conversations=_int(c, "conversations", name, minimum=1), arms=arms,
        summary=c["summary"], similarity_threshold=threshold, threshold_margin=margin,
        cache_reuse_n=_int(c, "cache_reuse_n", name, minimum=1), template_kwargs=_template_kwargs(c, name),
        corpus_dir=root / c["corpus_dir"], results_dir=root / c["results_dir"], hypotheses=tuple(hypotheses),
        registered_by=_registered_by(c["registered_by"], name), config_path=path,
    )


# --- model switch and restart (M6) ---------------------------------------------------------------

_M6_ID = re.compile(r"H-M6L[A-Za-z0-9]")
_M6_KEYS = ("repetitions", "child_context", "corpus_dir", "results_dir", "registered_by", "child_b", "hypotheses")
_M6_CHILD_KEYS = ("name", "hf_repo", "file", "sha256")
_M6_HYPOTHESIS_KEYS = ("mode", "models_max", "slots")
M6_MODES = ("router", "restart")


@dataclass(frozen=True)
class M6Hypothesis:
    """One process arrangement: `router` with its --models-max, or `restart` of a single server."""
    id: str
    mode: str
    models_max: int
    slots: int


@dataclass(frozen=True)
class M6Config:
    """Model switch and restart. Child A is the family under test; child B is pinned here."""
    repetitions: int
    child_context: int
    child_b: EngineModel
    corpus_dir: Path
    results_dir: Path
    hypotheses: tuple[M6Hypothesis, ...]
    registered_by: str
    config_path: Path

    def hypothesis(self, hid: str) -> M6Hypothesis:
        return _find(self.hypotheses, hid, "hypothesis", self.config_path.name)


def load_m6_config(path: Path, repo_root: Path) -> M6Config:
    path = Path(path)
    name = f"{path.name} [m6]"
    c = _read(path)["m6"]
    _require(c, _M6_KEYS, name)
    b = c["child_b"]
    _require(b, _M6_CHILD_KEYS, f"{name}.child_b")
    if not _SHA256.fullmatch(str(b["sha256"])):
        raise ValueError(f"{name}.child_b sha256 must be 64 hex characters")
    if not str(b["name"]).strip() or not str(b["file"]).strip():
        raise ValueError(f"{name}.child_b name and file must be non-empty")
    hypotheses = []
    for hid, h in (c.get("hypotheses") or {}).items():
        hname = f"{name}.hypotheses.{hid}"
        if not _M6_ID.fullmatch(hid):
            raise ValueError(f"{hname}: an id is H-M6L and one letter or digit for the configuration")
        _require(h, _M6_HYPOTHESIS_KEYS, hname)
        if h["mode"] not in M6_MODES:
            raise ValueError(f"{hname} mode must be one of {M6_MODES}, got {h['mode']!r}")
        models_max = _int(h, "models_max", hname, minimum=0)
        if h["mode"] == "router" and models_max < 1:
            raise ValueError(f"{hname}: a router cell needs models_max of 1 or more")
        if h["mode"] == "restart" and models_max != 0:
            raise ValueError(f"{hname}: a restart cell runs no router; models_max must be 0")
        hypotheses.append(M6Hypothesis(id=hid, mode=h["mode"], models_max=models_max,
                                       slots=_int(h, "slots", hname, minimum=1)))
    if not hypotheses:
        raise ValueError(f"{name} registers no hypothesis")
    root = Path(repo_root)
    return M6Config(
        repetitions=_int(c, "repetitions", name, minimum=1), child_context=_int(c, "child_context", name, minimum=1),
        child_b=EngineModel(family=str(b["name"]), hf_repo=str(b["hf_repo"]), file=str(b["file"]), sha256=str(b["sha256"])),
        corpus_dir=root / c["corpus_dir"], results_dir=root / c["results_dir"], hypotheses=tuple(hypotheses),
        registered_by=_registered_by(c["registered_by"], name), config_path=path,
    )
