# prefix-mortality — repo brief

Read `README.md` for what this is. `ledger/ledger.md` is the record and is append-only by numbered
entry; entry 0001 carries the scope, the claim under test and the registration rules, entry 0002
the controls' rules for llama.cpp, entries 0003 and 0004 their outcomes, and entry 0005 their
closure and the one-slot rule.

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
.venv/Scripts/python.exe -m prefix_mortality.controls probe --url URL    # bring an engine up; records nothing
.venv/Scripts/python.exe -m prefix_mortality.controls run --url URL --family qwen --model-path FILE
.venv/Scripts/python.exe -m prefix_mortality.summarize --run RUN_ID      # recomputes from disk; refuses on mismatch
.venv/Scripts/python.exe -m prefix_mortality.m1 probe --url URL --hypothesis H-M1L1 --sites system-0.240,user
.venv/Scripts/python.exe -m prefix_mortality.m1 run --url URL --hypothesis H-M1L1 --family qwen --model-path FILE
.venv/Scripts/python.exe -m prefix_mortality.summarize_m1 --run RUN_ID
```
On macOS/Linux the interpreter is `.venv/bin/python`. The project pins Python 3.12.

A driver's `run` refuses until a ledger entry registers its config: `config/controls.toml` and
`config/engines.toml` for the controls, and `config/m1.toml` as well for edit position. `m1 run`
also refuses a server that does not report the number of slots its hypothesis requires. After a
run, `manifest write`, then commit the new files under `corpus/`.

`tools/render_tau2_prefix.py` is not run by this venv: it needs an interpreter with tau2 installed
from a checkout at the pinned commit, with the package versions in
`corpus/base_prefix/tau2-airline/environment.txt`. It refuses to overwrite a fixture, and its hash is
in the fixture's provenance, so editing it turns `tests/test_base_prefix.py` red until a re-render.

## Layout
`src/prefix_mortality/` — `hashing` · `rng` · `seal` · `ledger_check` · `lint_scope` (chassis) ·
`config` (seal, controls, m1, engines) · `nonce` · `manifest` · `llamacpp` (engine client) · `record`
(request log) · `controls` (driver) · `summarize` (the rules, and the recomputation) · `edits` (one
word replaced at a named site) · `m1` (driver) · `summarize_m1` (its rules, and the recomputation).
`config/` — `seal.toml`, `controls.toml`, `m1.toml`, `engines.toml`. `ledger/` — `ledger.md`,
`predictions/`.
`corpus/` — `base_prefix/tau2-airline/`, `live/`, `requests/`, `MANIFEST.json`. `tools/` —
`render_tau2_prefix.py`. `results/` — gitignored past its placeholder.

## State
No hypothesis is registered. The controls (ledger 0002) ran on llama.cpp with two models and passed
on both: at the server's defaults every write and scramble reused 0 (ledger 0003); with the server
started with `--parallel 1` they reused the shared head and stayed within the bound (ledger 0004).
Ledger 0005 reads the cause in source (idle slots are cleared at the defaults), closes the controls,
and rules that an experiment depending on partial reuse runs with `--parallel 1`. Edit position is
built and tested against a stand-in server only; `config/m1.toml` is unregistered and no edit has
been sent to an engine. Next: `m1 probe` on the engine, then the entry that registers `H-M1L1` and
`H-M1LD`; that entry also adds their rows to the hypotheses table and their ids to
`ledger_check.REQUIRED_IDS`.
