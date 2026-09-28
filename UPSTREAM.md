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

## 2. Serving engine — `llama.cpp` — observed, not pinned

- Repo: https://github.com/ggml-org/llama.cpp
- `master` was observed at `6c7a87f7e5e5cd75b8a641c3471f2dee84a6ed17` and is recorded so a later pin
  can state what moved. `config/engines.toml` holds a placeholder; the registering entry records the
  commit the server was built from and the model files by sha256.

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
| ledger lint (structure, chain, block diff, cell provenance) | `…/ledger_check.py` | `…/ledger_check.py` | code unchanged |
| scope-sentence lint | `…/lint_scope.py` | `…/lint_scope.py` | mechanism verbatim; the sentence is this repo's |
| TOML → frozen config | `…/config.py` | `…/config.py` | seal loader verbatim; controls and engines loaders new |
| CI job | `.github/workflows/ci.yml` | same | package name; manifest step added |
| tests | `tests/{conftest,test_hashing,test_rng,test_seal,test_ledger_check}.py` | same names | package name |
| tests, adapted | `tests/{test_config,test_lint_scope,test_imports}.py` | same names | this repo's sentence, pins and loaders |
