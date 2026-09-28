# Ledger — prefix-mortality

Hypotheses are registered before any run. Verdicts are stated against the rule as written. Entries
are numbered, dated and immutable: an amendment is a new entry, never an edit. Status tags:
`[VALIDATED]` (ran, and survived an independent attempt to refute it), `[BASELINE]` (ran; numbers
here), `[STRETCH]` (designed, not run), `[FUTURE]` (not designed), `[SUPERSEDED]`.

From entry 0002 on, every entry records `prior-entries-sha256:` over the entries above it. A verdict
cell changes only by a line `verdict: H-XX = <VERDICT>` in a numbered entry. `ledger_check`
recomputes both in CI and refuses any edit to a committed entry.

A case a format or an instrument cannot evidence is recorded NOT MEASURABLE and enters neither a
numerator nor a denominator. It is never written as a zero.

## Hypotheses (pre-registered; verdict column is the only cell that ever changes, and only via a numbered entry)

| id | statement | decided by | verdict |
|---|---|---|---|

No hypothesis is registered yet.

## Entries

### 0001 — 2026-09-28 — Founding record: scope, claim under test, registration rules, base prefix

**Scope** (held verbatim in README.md): This repository measures how long a cached prompt prefix
survives and which registered change ends it, read from provider-reported usage and serving-engine
cache counters; it does not measure output quality or serving latency.

**Claim under test.** *A cached prefix has a measurable lifespan, and what ended it is stated per
request by three instruments of unequal reach: a serving engine's cache counters and a provider's
usage fields each give a token count and no reason; one provider's diagnostics name the first part of
the request that differs and estimate the tokens lost after it, and leave a miss with no difference
to be inferred*. The provider clause rests on two documentation pages read on 2026-09-28, listed in
`UPSTREAM.md` by address and sha256; the engine clause on llama.cpp's server README alone.

**Rules for every registration.**

1. Two controls pass on an instrument first: a byte-identical resend reads what the first request
   wrote, and a fresh random prefix of equal length reads nothing and writes something.
2. One hypothesis per cause per instrument, each with its own verdict cell; no pooled row. Ids are
   `H-M<n><letter>`: L llama.cpp, V vLLM, A Anthropic, O OpenAI.
3. An edit's position is the first token that differs under the instrument's own tokenizer.
4. A predicted read is computed from the prompt as the instrument renders it, not from the request.

**Base prefix** `[BASELINE]`. The system prompt and tool schemas of tau2-bench's airline domain,
rendered by tau2's own code at `b7ea9074c1cba482b30687fecdb5c8425fd6f619`, under
`corpus/base_prefix/tau2-airline/`:

| file | bytes | sha256 |
|---|---|---|
| `system.txt` | 8,033 | `54c8a8153c0f9fe4d2bc4d57a3698221d09388d84245afdcc253378ee4238cb2` |
| `tools.json` | 17,753 | `253e8390342cad1e556cfb04caec41815dcf9fa788dbbf5f6db0c870c9983cbb` |

It is a reconstruction: tau2-bench's published result files record no tool schemas and were produced
at commits absent from its public history. Its token length is NOT MEASURED on any model.

**Status.** Founded before any hypothesis was registered or any request sent; earlier working notes
are kept privately. The controls are `[STRETCH]`. Eight causes are `[FUTURE]`: edit position,
serialization drift, templating, idle expiry, rebuild, model switch, eviction under load, and
lifespan on recorded runs.
