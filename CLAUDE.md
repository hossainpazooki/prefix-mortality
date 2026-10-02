# prefix-mortality — repo brief

Read `README.md` for what this is. `ledger/ledger.md` is the record and is append-only by numbered
entry; entry 0001 carries the scope, the claim under test and the registration rules, entry 0002
the controls' rules for llama.cpp, entries 0003 and 0004 their outcomes, entry 0005 their closure
and the one-slot rule, entry 0006 the two hypotheses on edit position, entries 0007 and 0009 their
verdicts, entry 0008 rule 5 on `[VALIDATED]`, entries 0010 and 0011 the refuters' passes, and entry
0012 the hypothesis on eviction by intervening requests, entry 0013 its verdict, entry 0014 the
refuter's pass, entry 0015 the hypotheses on serialization drift and templating, and entries 0016
and 0017 their verdicts.

## Rules
- The chassis is copied from lag-ladder, not shared. Never import `lag_ladder`, `linear_ceiling` or
  `tau2`; `tests/test_imports.py` refuses it.
- Never write a number into the ledger or a doc that was not recomputed from `corpus/` or
  `results/`. A fact from outside the repo carries a primary source and a retrieval date, or the
  word "unverified".
- Not measurable is never zero. "Floor" or "bound" precedes any zero in prose.
- A narrow detector is a defect, not a null.
- One hypothesis per instrument; ids and the two binding rules are in ledger 0001.
- A result is `[BASELINE]` when stated; `[VALIDATED]` comes only from a later entry that names an
  independent refuter, its brief, what it tried and what survived (ledger 0008, rule 5).
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
.venv/Scripts/python.exe -m prefix_mortality.m7 probe --url URL --hypothesis H-M7LD --family qwen --ks 1,12
.venv/Scripts/python.exe -m prefix_mortality.m7 run --url URL --hypothesis H-M7LD --family qwen --model-path FILE
.venv/Scripts/python.exe -m prefix_mortality.summarize_m7 --run RUN_ID
.venv/Scripts/python.exe -m prefix_mortality.m2 probe --url URL --hypothesis H-M2L1 --changes S1,S3
.venv/Scripts/python.exe -m prefix_mortality.m2 run --url URL --hypothesis H-M2L1 --family qwen --model-path FILE
.venv/Scripts/python.exe -m prefix_mortality.summarize_m2 --run RUN_ID
.venv/Scripts/python.exe -m prefix_mortality.m3 probe --url URL --hypothesis H-M3LD --changes T1,T2
.venv/Scripts/python.exe -m prefix_mortality.m3 run --url URL --hypothesis H-M3LD --family qwen --model-path FILE
.venv/Scripts/python.exe -m prefix_mortality.summarize_m3 --run RUN_ID
```
On macOS/Linux the interpreter is `.venv/bin/python`. The project pins Python 3.12.

A driver's `run` refuses until a ledger entry registers its config: `config/controls.toml` and
`config/engines.toml` for the controls, and `config/m1.toml`, `config/m2.toml`, `config/m3.toml` or
`config/m7.toml` as well for edit position, serialization drift, templating or eviction. Every
experiment's `run` also refuses a server that does not report the number of slots its hypothesis
requires; `m7 run` refuses one that reports no slot context, and sends no trial whose anchor does not
fit it. After a run, `manifest write`, then commit the new files under `corpus/`.

`tools/render_tau2_prefix.py` is not run by this venv: it needs an interpreter with tau2 installed
from a checkout at the pinned commit, with the package versions in
`corpus/base_prefix/tau2-airline/environment.txt`. It refuses to overwrite a fixture, and its hash is
in the fixture's provenance, so editing it turns `tests/test_base_prefix.py` red until a re-render.

## Layout
`src/prefix_mortality/` — `hashing` · `rng` · `seal` · `ledger_check` · `lint_scope` (chassis) ·
`config` (seal, controls, m1, m7, engines) · `nonce` · `manifest` · `llamacpp` (engine client) ·
`record` (request log) · `controls` (driver) · `summarize` (the rules, and the recomputation) · `edits`
(one word replaced at a named site) · `m1` (driver) · `summarize_m1` (its rules, and the recomputation)
· `m7` (driver: anchor, K foreign requests, resend) · `summarize_m7` (its rule, and the recomputation)
· `serialize` (the six re-serializations of the tools) · `pairs` (two-request evaluation shared by M2
and M3) · `m2`, `summarize_m2` (serialization drift) · `m3`, `summarize_m3` (templating).
`config/` — `seal.toml`, `controls.toml`, `m1.toml`, `m2.toml`, `m3.toml`, `m7.toml`, `engines.toml`.
`ledger/` — `ledger.md`, `predictions/`.
`corpus/` — `base_prefix/tau2-airline/`, `live/`, `requests/`, `MANIFEST.json`. `tools/` —
`render_tau2_prefix.py`. `results/` — gitignored past its placeholder.

## State
The controls (ledger 0002) ran on llama.cpp with two models and passed
on both: at the server's defaults every write and scramble reused 0 (ledger 0003); with the server
started with `--parallel 1` they reused the shared head and stayed within the bound (ledger 0004).
Ledger 0005 reads the cause in source (idle slots are cleared at the defaults), closes the controls,
and rules that an experiment depending on partial reuse runs with `--parallel 1`. Ledger 0006
registers edit position as `H-M1L1` (one slot) and `H-M1LD` (the defaults). Both are HELD on both
models (ledger 0007, 0009): with one slot every trial reused exactly the tokens before the first one
that differed; at the defaults it reused them above about a tenth of the prompt and nothing below,
the change bracketed between 0.0945 and 0.1048 of the prompt. Ledger 0008 adds rule 5: `[VALIDATED]`
only through an independent refuter's entry; 0010 and 0011 record the refuters' passes, and both
hypotheses are `[VALIDATED]`. Eviction by intervening requests (M7: an anchor, K foreign requests one
at a time, the anchor again) is `H-M7LD`, registered by ledger 0012 at the defaults only and HELD on
both models (ledger 0013): the resend reused *n* − 1 at every *K* up to 11 and 0 from *K* = 12, where
the anchor and the first *K* − 1 foreign prompts stop fitting in the 8192 MiB prompt cache. It is
`[VALIDATED]` (ledger 0014). Serialization drift (M2: six re-serializations of the tools) and
templating (M3: a date argument and a thinking switch)
are `H-M2L1` (one slot) and `H-M3L1`, `H-M3LD` (one slot, defaults), registered by ledger 0015 and
HELD on both models (0016, 0017): re-indenting or reordering a tool's keys changes nothing, reordering
the tools or a schema's properties ends the prefix at that point; Llama's template date, the 24th
token, ends the whole prefix at the defaults, and Qwen's thinking switch costs the last four tokens.
All three are `[BASELINE]`, no refuter yet. Four causes remain `[FUTURE]`.
