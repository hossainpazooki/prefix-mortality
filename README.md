# prefix-mortality

How long does a cached prompt prefix live, and what kills it?

Agent runs resend nearly the same context on every request. Exact-match prefix caching, in a
provider's API or in a serving engine, turns that repetition into a discount, and it matches on bytes.
A reordered key, a timestamp in the system prompt, an idle gap or a model change ends the match while
the content stays where it was. A hit rate says that a prefix missed. It does not say why.

## What is measured, and where it is read

The scope sentence, held verbatim: This repository measures how long a cached prompt prefix survives
and which registered change ends it, read from provider-reported usage and serving-engine cache
counters; it does not measure output quality or serving latency.

A field an instrument does not carry is recorded NOT MEASURABLE. It is never a zero.

## How a death is measured

Each cause is one registered experiment per instrument: the change is applied once, to a known
prefix, and the result is read off that instrument. Before any of them runs, two controls must pass
on the same instrument:

- **identity** — the same bytes sent twice; the second request reads what the first one wrote;
- **scramble** — fresh random text of the same length; nothing is read, and something is written.

If either fails, the instrument cannot see a death and no table is produced.

## Status

The record-keeping, the starting prefix and the two controls exist. The controls have run on one
serving engine with two models and passed on both, at the server's defaults and again with one slot.
Reuse of part of a prompt is on record with one slot only; at its defaults the engine clears an idle
slot, which the ledger reads from its source. The controls are closed. One cause, the position of
an edit, is registered as two hypotheses, one per server configuration. With one slot it is
measured and held on both models: the engine reuses exactly the tokens before the first one that
differs. At the engine's defaults its outcome is not stated yet. `ledger/ledger.md` is the record of
what has been registered and measured, and it says what has not.

## How the record stays auditable

- `ledger/ledger.md` — numbered, dated, immutable entries; hypotheses registered before any run;
  every entry hashes the ones above it, and CI refuses an edit to a committed entry.
- `ledger/predictions/` — sealed pre-run predictions (`python -m prefix_mortality.seal`).
- `config/*.toml` — every seed and threshold; nothing numeric lives in code.
- `corpus/` — the base prefix, and later the request log; `corpus/MANIFEST.json` is checked against
  disk in both directions (`python -m prefix_mortality.manifest check`).
- `UPSTREAM.md` — every pin, and where each copied module came from.

## Setup

```
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"     # Windows: .venv/Scripts/python.exe
.venv/bin/python -m pytest -q
```

## License

Apache-2.0; see `LICENSE`. The starting prefix under `corpus/base_prefix/` comes from tau2-bench,
which is MIT; see `NOTICE`.
