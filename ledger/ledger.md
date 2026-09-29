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

### 0002 — 2026-09-29 — Controls registered on llama.cpp b11235, two models

prior-entries-sha256: 18adec6a073405db0d76791bce243cf7a2b8e6825afef0f0096dd3ee2027a09e

**Registers** `config/controls.toml` and `config/engines.toml`, both now `registered_by = "0002"`.
No hypothesis is registered and no verdict cell is added: a control's outcome per model is PASS, FAIL
or NOT MEASURABLE, and a later entry states it from `summarize` output.

**Instrument.**

| part | value |
|---|---|
| engine | llama.cpp release `b11235`, commit `6c7a87f7e5e5cd75b8a641c3471f2dee84a6ed17`. |
| download | `llama-b11235-bin-macos-arm64.tar.gz`, sha256 `d28351029acd7e0c01825d8e7dddadded3da4a2494bf72ebd98e73aec9344d50`. |
| server flags | None but the model file. Slots, context size and every other setting are the server's defaults, and each record stores what the server reports about itself. |
| model, family `qwen` | `Qwen3-8B-Q4_K_M.gguf`, sha256 `d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785`. |
| model, family `llama` | `Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf`, sha256 `7b064f5842bf9532c91456deda288a1b672397a54fa729aa665952863033557c`. |
| machine | Apple M6, 16 GB of memory, macOS 27.0.1. |

The driver refuses a model file that does not hash to its pin, and a server whose build is not the
pinned one.

**Parameters**, as in `config/controls.toml`: 5 repetitions per model, each a write, a read and a
scramble; one generated token; temperature 0; a fresh 16-byte nonce per repetition ahead of the
system text, and another for the scramble; scramble words drawn with seed 0; length tolerance 16
tokens.

**Rules.** *n* is the token count of the prompt as the server renders it. *h* is the count of tokens
that start before the end of the nonce.

| request | passes when |
|---|---|
| write | Reuse is at most *h*. |
| read, the same bytes again | Reuse is exactly *n* − 1. |
| scramble | Reuse is at most *h*, and its *n* is within the tolerance of the write's. |
| each of the three | Reused and processed tokens add up to *n*, and the server's two reuse fields agree. |
| a field the server does not report | The run is NOT MEASURABLE. |

These rules state rule 1 of entry 0001 for this engine. "Reads what the first request wrote" is
*n* − 1 and not *n*: the server processes the last token of a prompt it already holds
(`tools/server/server-context.cpp` at the pinned commit). "Reads nothing" is a bound of *h* and not
0: every prompt of one model begins with the same template text.

**Known before the run.**

| fact | consequence |
|---|---|
| The server gives a prompt to the slot holding the most similar one, or else to an empty or least recently used slot. | A write or a scramble that meets an empty slot reuses 0. That satisfies the bound without testing it against a held prompt. The results entry states the reuse of every request, not only the outcome. |
| The Llama 3.1 template prints the machine's local date ahead of the system text. | A run that crosses local midnight halts, because the same request renders differently. Such a halt is reported as a halt, not as a failed control. |
| One unrecorded pair of requests per model was sent before this entry, to confirm the field names. | Nothing from it is evidence and no figure from it appears here. The rules are those of `src/prefix_mortality/summarize.py` as committed at `454e181`, before that contact. |

**Status.** The controls are `[STRETCH]`: registered, not run.
