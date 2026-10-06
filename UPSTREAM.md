# Upstreams (read-only) and chassis provenance

`src/prefix_mortality/__init__.py` is the single source of truth for every sha below;
`tests/test_imports.py` asserts this file names exactly those shas.

## 1. Base prefix source — `tau2-bench` (rendered once, never imported)

- Repo: https://github.com/sierra-research/tau2-bench (MIT)
- Pinned commit: `b7ea9074c1cba482b30687fecdb5c8425fd6f619`
- Taken from it: the airline domain's system prompt and tool schemas, rendered by tau2's own code in
  a separate environment by `tools/render_tau2_prefix.py` and committed under
  `corpus/base_prefix/tau2-airline/`. `provenance.json` carries the output hashes and the versions of
  the packages that shape the schema text; `environment.txt` is the full package list.
- The rendering environment needs one package tau2 does not list among its base dependencies,
  `websockets`, which tau2's package import reaches unconditionally.
- What it cannot give: the bytes the published result files' runs sent. The fixture is a
  reconstruction at a public commit and is labelled so wherever it is used.
- Also taken from it, at the same commit: `data/tau2/results/final/claude-3-7-sonnet-20250219_airline_default_gpt-4.1-2025-04-14_4trials.json`
  (10,551,448 bytes, sha256 `40a2c6a246eab27db5cdefda895fbe7f44be78a23d300817248534aa606d66de`),
  of which the 50 simulations with `trial == 0` are vendored under
  `corpus/recorded/tau2-airline-claude-3-7-sonnet/` by `prefix_mortality.recorded extract` with
  each message's `raw_data` dropped; `provenance.json` there carries the source hash and the
  output hash. These are trajectories: their `usage` fields carry no cache count.

## 2. Serving engine — `llama.cpp` (run as a separate process, never linked)

- Repo: https://github.com/ggml-org/llama.cpp
- Pinned: release `b11235`, built from `6c7a87f7e5e5cd75b8a641c3471f2dee84a6ed17`. The download and
  its digest, and the two model files and theirs, are in `config/engines.toml`.
- Run at the server's defaults. The driver refuses a server that reports another build, and a model
  file that does not hash to the configured digest.
- Read at the pinned commit, and relied on: the server's README for the response fields;
  `tools/server/server-context.cpp` for how reuse is counted and for the template endpoint;
  `common/chat.cpp` for what is passed into a chat template.

## 3. Provider documentation — read, not vendored

Fetched as raw text on 2026-09-28; the hash identifies what was read.

| page | bytes | sha256 |
|---|---|---|
| `https://platform.claude.com/docs/en/build-with-claude/prompt-caching.md` | 159,255 | `78d10f9ffe8ebd5d3674a3f41e613852427f3605ce04c45d071949dfc2032213` |
| `https://platform.claude.com/docs/en/build-with-claude/cache-diagnostics.md` | 47,224 | `03aa15828276eed4269f366c11ba0f26b0c48ccaa34d031c6ede6a1ca4b4f2b8` |

## 4. Chassis — copied from `lag-ladder`

- Repo: https://github.com/hossainpazooki/lag-ladder, copied at
  `e8444944c5698cb64f1065eb7202307221358461`. lag-ladder copied it from
  https://github.com/hossainpazooki/linear-ceiling.
- Copied, not shared, so a change in either repo is not a change here.

| what | source path | here | change |
|---|---|---|---|
| canonical JSON bytes + sha256 helpers | `src/lag_ladder/hashing.py` | `src/prefix_mortality/hashing.py` | verbatim (package name) |
| the one seeded generator | `…/rng.py` | `…/rng.py` | verbatim |
| pre-run seal (write / require / verify) | `…/seal.py` | `…/seal.py` | verbatim; a "pair" is an experiment id |
| ledger lint (structure, chain, block diff, cell provenance) | `…/ledger_check.py` | `…/ledger_check.py` | code unchanged; `REQUIRED_IDS` is this repo's |
| scope-sentence lint | `…/lint_scope.py` | `…/lint_scope.py` | mechanism verbatim; the sentence is this repo's |
| TOML → frozen config | `…/config.py` | `…/config.py` | seal loader verbatim; controls, m1 and engines loaders new |
| CI job | `.github/workflows/ci.yml` | same | package name; manifest step added |
| tests | `tests/{conftest,test_hashing,test_rng,test_seal}.py` | same names | package name |
| tests | `tests/test_ledger_check.py` | same name | package name; the cases on built ledgers run with no required id, and one case checks this repo's ids |
| tests, adapted | `tests/{test_config,test_lint_scope,test_imports}.py` | same names | this repo's sentence, pins and loaders |
