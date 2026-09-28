# prefix-mortality — repo brief

Read `README.md` for what this is. `ledger/ledger.md` is the record and is append-only by numbered
entry; entry 0001 carries the scope, the claim under test and the registration rules.

## Rules
- The chassis is copied from lag-ladder, not shared. Never import `lag_ladder`, `linear_ceiling` or
  `tau2`; `tests/test_imports.py` refuses it.
- Never write a number into the ledger or a doc that was not recomputed from `corpus/` or
  `results/`. A fact from outside the repo carries a primary source and a retrieval date, or the
  word "unverified".
- Not measurable is never zero. "Floor" or "bound" precedes any zero in prose.
- A narrow detector is a defect, not a null.
- One hypothesis per instrument; ids and the two binding rules are in ledger 0001.
- Seeds and thresholds live in `config/*.toml`. Seeded randomness only via
  `prefix_mortality.rng.make_rng`; the per-run nonce only via `prefix_mortality.nonce.new_nonce`.
- A config with `registered_by = ""` is UNREGISTERED; no driver may run while it is empty. A
  `*_PENDING` pin is refused by name.
- Never edit a committed ledger entry or a sealed prediction; append.
- Ledger entries are short: what was registered, ruled or measured, its sources, its status.
- Keys live in `.env`, which is gitignored. Never write one to a log, a record or the terminal.
- Build what the next step calls. A module nothing imports does not belong here yet.

## Commands
```
.venv/Scripts/python.exe -m pytest -q                       # suite (synthetic, offline)
.venv/Scripts/python.exe -m prefix_mortality.seal verify
.venv/Scripts/python.exe -m prefix_mortality.lint_scope
.venv/Scripts/python.exe -m prefix_mortality.manifest check # `write` after adding corpus files
.venv/Scripts/python.exe -m prefix_mortality.ledger_check   # --against <rev> in CI
```
On macOS/Linux the interpreter is `.venv/bin/python`. The project pins Python 3.12.

`tools/render_tau2_prefix.py` is not run by this venv: it needs an interpreter with tau2 installed
from a checkout at the pinned commit, with the package versions in
`corpus/base_prefix/tau2-airline/environment.txt`. It refuses to overwrite a fixture, and its hash is
in the fixture's provenance, so editing it turns `tests/test_base_prefix.py` red until a re-render.

## Layout
`src/prefix_mortality/` — `hashing` · `rng` · `seal` · `ledger_check` · `lint_scope` (chassis) ·
`config` (seal, controls, engines) · `nonce` · `manifest`.
`config/` — `seal.toml`, `controls.toml`, `engines.toml`. `ledger/` — `ledger.md`, `predictions/`.
`corpus/` — `base_prefix/tau2-airline/`, `live/`, `requests/`, `MANIFEST.json`. `tools/` —
`render_tau2_prefix.py`. `results/` — gitignored past its placeholder.

## State
Nothing has run and no hypothesis is registered. Next: the record writer, one engine client, the two
controls, and a summarizer for their output.
