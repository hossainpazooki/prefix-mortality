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

### 0003 — 2026-09-29 — Controls pass on both models; a one-slot repetition is registered

prior-entries-sha256: ba245546231ed73daed1dbf9e46ef2ed34ab9becff4228f72e4be480303d66c1

**Outcome** `[BASELINE]`. The controls registered by 0002 ran at commit `9fa3226`. Their records and
requests are committed at `6fd42e0`. Every figure below is from `summarize --run` on those files, or
from the `server` field of the records.

| | `qwen` | `llama` |
|---|---|---|
| run | `20260929T205253Z-qwen` | `20260929T205508Z-llama` |
| outcome | PASS | PASS |
| requests | 15 | 15 |
| read: reuse is *n* − 1 | 5 of 5 | 5 of 5 |
| write: reuse | 0 in 5 of 5 | 0 in 5 of 5 |
| scramble: reuse | 0 in 5 of 5 | 0 in 5 of 5 |
| *n* | 4,868 to 4,872 | 5,644 to 5,650 |
| *h* | 31 to 35 | 47 to 53 |
| largest gap, scramble *n* against write *n* | 3 | 6 |
| slots, as the server reported | 4 | 4 |
| context, as the server reported | 40,960 | 50,944 |
| fields not reported | None. | None. |

**What the outcome does not show.** The bound of *h* was met only at its floor of 0. No write and no
scramble reused a token, so the bound never faced a value that could have exceeded it. The server
reported 4 slots and each run sent 10 fresh prompts, so at least 6 per run were served by a slot that
had already served a request. All of them reused 0. Whether such a slot still held its earlier prompt
when the new one arrived is not recorded, and why nothing of a shared template head was reused is not
established.

**Registers** one repetition of the controls with the server started with `--parallel 1`. That flag
is the only override. Engine, models, parameters and rules are those of 0002.

| question | how it is answered |
|---|---|
| Does a write or a scramble that meets a held prompt reuse its shared head, and stay within *h*? | With one slot, every request after the first is served by the slot that holds the previous prompt. The results entry states the reuse of every request. |
| Was the run made with one slot? | Each record stores the number of slots the server reported. A run whose records do not say 1 is not this repetition. |
| What would leave the question open? | A reuse of 0 on every write and scramble. The bound would then be untested on this engine with one slot as well as with four. |

Unrecorded requests were sent to a one-slot server before this entry. Nothing from them is evidence
and no figure from them appears here.

**Status.** The controls at the server's defaults are `[BASELINE]`. The one-slot repetition is
`[STRETCH]`: registered, not run.

### 0004 — 2026-09-29 — The one-slot repetition passes; the bound is met above its floor

prior-entries-sha256: 3ed86e31dfa3124157736da078d8eb885d3e727a83d0ede9fca9dc706298d074

**Outcome** `[BASELINE]`. The repetition registered by 0003 ran at commit `3b56280`. Its records and
requests are committed at `666595b`. Every figure below is from `summarize --run` on those files, or
from the `server` field of the records.

| | `qwen` | `llama` |
|---|---|---|
| run | `20260929T211825Z-qwen` | `20260929T212012Z-llama` |
| outcome | PASS | PASS |
| requests | 15 | 15 |
| slots, as the server reported | 1 | 1 |
| read: reuse is *n* − 1 | 5 of 5 | 5 of 5 |
| write and scramble: reuse above 0 | 9 of 10 | 9 of 10 |
| write and scramble: reuse at most *h* | 10 of 10 | 10 of 10 |
| *n* | 4,866 to 4,872 | 5,645 to 5,655 |
| *h* | 30 to 35 | 48 to 55 |
| largest gap, scramble *n* against write *n* | 4 | 7 |
| context, as the server reported | 40,960 | 50,944 |
| fields not reported | None. | None. |

Reuse of each write and each scramble, against the *h* of the same request:

| repetition | `qwen` write | `qwen` scramble | `llama` write | `llama` scramble |
|---|---|---|---|---|
| 1 | 0 of 35 | 5 of 35 | 0 of 52 | 31 of 49 |
| 2 | 4 of 32 | 4 of 32 | 31 of 50 | 31 of 49 |
| 3 | 7 of 34 | 4 of 34 | 32 of 48 | 31 of 50 |
| 4 | 4 of 30 | 4 of 33 | 31 of 51 | 32 of 50 |
| 5 | 4 of 34 | 4 of 33 | 33 of 51 | 32 of 55 |

**What it shows.** The question of 0003 is answered for one slot. A write or a scramble that follows
another prompt reuses the head the two share, 4 to 7 tokens on `qwen` and 31 to 33 on `llama`, and
stays within *h*. The only request of each run that reused 0 is its first.

**What stays open.** With four slots the same kind of request reused 0 (entry 0003). What differs
between one slot and four is not established. Reuse of part of a prompt is on record for this engine
with one slot only.

**Status.** The two controls are `[BASELINE]` on both models, at the server's defaults and with one
slot. No hypothesis is registered.
