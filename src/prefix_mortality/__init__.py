"""prefix-mortality: the ledger, seal, gates and config for measuring how long a cached prompt prefix
survives and which registered change ends it.

Nothing here sends a request or starts a server yet. The chassis is copied from lag-ladder with
provenance (UPSTREAM.md). tau2 is run once, in its own environment, by tools/render_tau2_prefix.py,
and is never imported from this package.
"""
from pathlib import Path

__version__ = "0.0.1"

# src/prefix_mortality/__init__.py -> repo root is three parents up.
REPO_ROOT = Path(__file__).resolve().parents[2]

# Single source of truth for every pin; UPSTREAM.md repeats them for humans and tests/test_imports.py
# asserts the two agree (every 40-hex sha in UPSTREAM.md is one of these, and each of these is there).
CHASSIS_REPO = "https://github.com/hossainpazooki/lag-ladder"
CHASSIS_SHA = "e8444944c5698cb64f1065eb7202307221358461"          # the commit the chassis modules were copied at

BASE_PREFIX_REPO = "https://github.com/sierra-research/tau2-bench"
BASE_PREFIX_SHA = "b7ea9074c1cba482b30687fecdb5c8425fd6f619"      # PINNED; corpus/base_prefix/ was rendered from it

ENGINE_REPO = "https://github.com/ggml-org/llama.cpp"
ENGINE_SHA = "6c7a87f7e5e5cd75b8a641c3471f2dee84a6ed17"           # release b11235; PINNED (config/engines.toml)
