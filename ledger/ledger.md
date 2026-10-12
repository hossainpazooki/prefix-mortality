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
| H-M1L1 | On llama.cpp `b11235` started with `--parallel 1`, a request that differs from the prompt the slot holds reuses exactly the tokens before the first one that differs. | entry 0006 | HELD |
| H-M1LD | On llama.cpp `b11235` at its defaults, the same request reuses those tokens when they are more than 0.10 of its length, and none otherwise. | entry 0006 | HELD |
| H-M7LD | On llama.cpp `b11235` at its defaults, a request identical to one served earlier reuses *n* − 1 tokens when the KV states of the earlier request and of the foreign requests served between them, one at a time, fit in the 8192 MiB prompt cache, and 0 when they do not. | entry 0012 | HELD |
| H-M2L1 | On llama.cpp `b11235` started with `--parallel 1`, a request whose tool schemas are written differently reuses exactly the common token prefix of its rendered prompt with the base request's, and *n* − 1 when the two render identically. | entry 0015 | HELD |
| H-M3L1 | On llama.cpp `b11235` started with `--parallel 1`, a request that differs from the held prompt only in a chat-template argument reuses exactly the common token prefix of the two rendered prompts, and *n* − 1 when they render identically. | entry 0015 | HELD |
| H-M3LD | On llama.cpp `b11235` at its defaults, the same request reuses that prefix when it is more than 0.10 of its length, and none otherwise. | entry 0015 | HELD |
| H-M4LD | On llama.cpp `b11235` at its defaults, a request identical to one served *g* seconds earlier, with nothing served between them, reuses *n* − 1 tokens at every registered *g* (0, 2, 4, 60, 600). | entry 0019 | HELD |
| H-M4LS | On llama.cpp `b11235` started with `--sleep-idle-seconds 60`, the same request reuses *n* − 1 tokens after a gap of 20 seconds and 0 after a gap of 100 seconds, the server reporting sleeping in between. | entry 0019 | HELD |
| H-M1V32 | On vLLM `b6d8e8af` (CPU backend) started with `--block-size 32`, a request that differs from an earlier one at token *d* reads cached = floor(min(*d*, *n* − 1)/32)·32 and creates floor(*n*/32)·32 minus that. | entry 0025 | HELD |
| H-M1V128 | On vLLM `b6d8e8af` (CPU backend) started with `--block-size 128`, the same request reads cached = floor(min(*d*, *n* − 1)/128)·128 and creates floor(*n*/128)·128 minus that. | entry 0025 | HELD |
| H-M1L1Q17 | On llama.cpp `b11235` started with `--parallel 1` serving the qwen17 family (0028), a request that differs from the prompt the slot holds reuses exactly the tokens before the first one that differs. | entry 0030 | HELD |
| H-M1LDQ17 | On llama.cpp `b11235` at its defaults serving the qwen17 family, the same request reuses those tokens when they are more than 0.10 of its length, and none otherwise. | entry 0030 | HELD |
| H-M3V32 | On vLLM `b6d8e8af` (CPU backend) started with `--block-size 32`, a request that differs from an earlier one only in a chat-template argument reads cached = floor(min(*d*, *n* − 1)/32)·32 and creates floor(*n*/32)·32 minus that, *d* the leading tokens the two rendered prompts share. | entry 0035 | HELD |
| H-M3V128 | The same at `--block-size 128`, with 128 in the formula. | entry 0035 | HELD |
| H-M2V32 | On vLLM `b6d8e8af` (CPU backend) started with `--block-size 32`, a request whose tool schemas are written differently but carry the same JSON value reads cached = floor(min(*d*, *n* − 1)/32)·32 and creates floor(*n*/32)·32 minus that, under the same *d*. | entry 0035 | HELD |
| H-M2V128 | The same at `--block-size 128`, with 128 in the formula. | entry 0035 | HELD |
| H-M8L1 | On llama.cpp `b11235` started with `--parallel 1`, fifty recorded tau2-bench airline conversations replayed one request per assistant turn, one after another and with no nonce, reuse per request what the pinned server's slot and prompt-cache policy predicts from the stored token lists: the common prefix with the held prompt, the shared head across conversations included. | entry 0038 | HELD |
| H-M8LD | The same at the server's defaults (4 slots, 8192 MiB prompt cache) with the C longest conversations interleaved in round robin, C in {2, 6, 12}: reuse per request what the same policy predicts, the slot choice by similarity, the cache searched only when under half of the held prompt would be kept, restores and evictions by the registered geometry. | entry 0038 | HELD |
| H-M5L1 | On llama.cpp `b11235` started with `--parallel 1`, a recorded conversation sent in full and then compacted at its midpoint — the early turns trimmed, or replaced by one summary message — reuses, for the compacted request, exactly the tokens the two prompts share from the start. | entry 0039 | HELD |
| H-M5LD | The same at the server's defaults: that prefix when it is above 0.10 of the compacted request, else 0. | entry 0039 | HELD |
| H-M5LC | The same started with `--parallel 1 --cache-reuse 256`: that prefix plus every later run of at least 256 matching tokens shifted into place — the trimmed tail whole, nothing past an inserted summary. | entry 0039 | HELD |
| H-M6LA | On llama.cpp `b11235` in router mode with `--models-max 4`, the base request sent to child A, its messages to child B, then A again: B reuses nothing, and A again reuses *n* − 1 — a model switch ends the match for the request that switched and not for the one that switches back, while the child stays loaded. | entry 0040 | HELD |
| H-M6LB | The same with `--models-max 1`: loading B unloads A, and A again reuses 0. | entry 0040 | HELD |
| H-M6LR | On llama.cpp `b11235` with one slot and `--slot-save-path`, the base request resent after the process is stopped and started reuses 0; with the slot saved before the stop and restored after, *n* − 1. | entry 0040 | HELD |

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

### 0005 — 2026-09-29 — Why four slots reused nothing; the controls are closed

prior-entries-sha256: 2ece93bd004b76c3ba27eb5d9ac2a9527f01a89f93452179557db3b7f8757dd7

**Cause of the zeros in 0003.** Read in llama.cpp at the pinned commit
`6c7a87f7e5e5cd75b8a641c3471f2dee84a6ed17`, in `tools/server/README.md`, `tools/server/server-context.cpp`
and `tools/server/server-task.cpp`. It is a reading of source, not a measurement.

| default of the server | what it does | where it is read |
|---|---|---|
| The number of slots is automatic, and the slots then share one buffer. | The records of 0003 say 4 slots. | README, `--parallel` and `--kv-unified`. |
| `--cache-idle-slots` is enabled. | When a request starts on one slot, every idle slot is copied to the prompt cache in memory and, with a shared buffer, cleared. | README, `--cache-idle-slots`; `server-context.cpp`, the block tagged `TAG_IDLE_SLOT_CLEAR`. |
| A request is given the slot whose prompt it resembles only above a similarity of 0.10. | A prompt with a fresh nonce at its head resembles none, and is given the least recently used slot, which has been cleared. | README, `--slot-prompt-similarity`; `server-context.cpp`, `get_available_slot`. |
| A prompt is restored from the cache only if at least a quarter of it would be kept. | A prompt that shares only a template head with a cached one restores nothing. | `server-task.cpp`, `server_prompt_cache::load`. |

So at the defaults a write or a scramble starts from an empty slot and reuses 0, as 0003 recorded.
With `--parallel 1` no slot is idle when a request starts and the buffer is not shared, so the slot
keeps its prompt and the next request reuses the head the two share, as 0004 recorded.

One unrecorded run with the server's logging raised was made after 0004. Nothing from it is evidence
and no figure from it appears here.

**What this reading predicts and no run has tested.** At the defaults the reuse after a change to a
prompt depends on the two thresholds above as well as on where the change is. NOT MEASURED.

**Ruled by the operator, 2026-09-29.**

1. The controls are closed on llama.cpp `b11235` for both models.
2. An experiment that depends on reuse of part of a prompt runs on a server started with
   `--parallel 1`. Its registering entry names the flag, and a run whose records do not say 1 slot
   is not that experiment.

**Status.** The controls are closed, `[BASELINE]`. No hypothesis is registered. The eight causes of
0001 are `[FUTURE]`.

### 0006 — 2026-09-29 — Edit position registered on llama.cpp: H-M1L1 and H-M1LD

prior-entries-sha256: eeadbe3f9daf6916ea61a0a74f67ce200170456f8e525d7a5f2b5f0021d9d6de

**Registers** `config/m1.toml`, now `registered_by = "0006"`, and two hypotheses, each with its own
verdict cell. Engine, models and machine are those of 0002. The request parameters are those of
`config/controls.toml`.

**Ids.** Rule 2 of 0001 gives `H-M<n><letter>`. One character is added for the server's
configuration: `1` for one slot, `D` for the defaults. Ruled by the operator on 2026-09-29: the two
configurations are separate hypotheses, and the two models are cells inside each.

| id | server | the records must say | predicted reuse of the edited request |
|---|---|---|---|
| `H-M1L1` | Started with `--parallel 1`. | 1 slot. | *d*. |
| `H-M1LD` | Started with no flag but the model. | 4 slots. | *d* when *d* / *n* is above 0.10, and 0 otherwise. |

*d* is the number of leading tokens the base prompt and the edited prompt have in common, under the
server's own tokenizer, each prompt as the server renders it. *n* is the token count of the edited
prompt. The 0.10 is the server's `--slot-prompt-similarity` at its default (entry 0005).

**A trial** is two requests under one fresh nonce: the base request, then the same request with one
word replaced by `zebra`, a word that occurs nowhere in the base prefix. The 13 sites are the word at
0, 0.1, 0.24, 0.27, 0.32, 0.5, 0.75 and 0.999 of the system text's length; the first word of the
description of tools 0, 4, 9 and 13; and the first word of the user message. Each site is tried 5
times: 65 trials and 130 requests per model, per hypothesis.

**What decides.**

| case | rule |
|---|---|
| A trial matches. | The edited request's reuse equals its prediction, the server's two counts add up to *n*, and its two reuse fields agree. |
| `HELD` | Every counted trial of both models matches. |
| `NOT CONFIRMED` | At least one counted trial does not match. The results entry states the prediction and the reuse of every trial. |
| A trial is not counted. | Its *d* / *n* lies within 0.002 of 0.10, under `H-M1LD` only. It is reported. |
| A control fails. | The base request reuses more than *h*, the tokens that start before the end of the nonce. The run stops, and no verdict follows from it. |
| NOT MEASURABLE | The server does not report a field. The verdict stays `unresolved`. |
| The records say another number of slots. | The run is not that experiment. |

A prediction is a function of the two stored prompts and the rule above, and of nothing else.
`summarize_m1` recomputes it from the stored tokens and refuses a record that carries another value.

**Known before the run.**

| fact | consequence |
|---|---|
| The prediction for the defaults rests on the reading of source in 0005. | If the reading is wrong or incomplete, `H-M1LD` is NOT CONFIRMED, and the results entry states what was observed. |
| The server's properties do not say whether its slots share a buffer or whether idle slots are cleared. | The records cannot tell a server at its defaults from one started with four slots by flag. The run is started with no flag but the model. |
| Unrecorded requests of this kind were sent to both configurations before this entry. | Nothing from them is evidence and no figure from them appears here. The rules and the sites are those committed at `a0e31df`, before that contact. |

**Status.** `H-M1L1` and `H-M1LD` are `[STRETCH]`: registered, not run. `H-M1L1` runs first.

### 0007 — 2026-09-29 — H-M1L1 held: with one slot, reuse is the position of the edit

prior-entries-sha256: 5f726bab5bdaf12d6cd22a191b88a262e9e20ab3764c2534a6c710ab62a4e9d4

verdict: H-M1L1 = HELD

**Outcome** `[BASELINE]`. The runs registered by 0006 for `H-M1L1` were made at commit `d36bf8c`, on
a server started with `--parallel 1`. Their records and requests are committed at `be52eca`. Every
figure below is from `summarize_m1 --run` on those files, or from the `server` field of the records.

| | `qwen` | `llama` |
|---|---|---|
| run | `20260929T234127Z-qwen-H-M1L1` | `20260929T235847Z-llama-H-M1L1` |
| outcome | ALL MATCH | ALL MATCH |
| trials counted | 65 | 65 |
| trials matching | 65 | 65 |
| trials not counted | 0 | 0 |
| base request within *h* | 65 of 65 | 65 of 65 |
| slots, as the server reported | 1 | 1 |
| context, as the server reported | 40,960 | 50,944 |
| *n* | 4,864 to 4,873 | 5,644 to 5,652 |
| fields not reported | None. | None. |

Tokens reused by the edited request. In every trial it is the prediction, *d*:

| site | `qwen` | `llama` | trials matching |
|---|---|---|---|
| `system-0.000` | 29 to 36 | 50 to 53 | 10 of 10 |
| `system-0.100` | 217 to 220 | 226 to 231 | 10 of 10 |
| `system-0.240` | 460 to 463 | 469 to 474 | 10 of 10 |
| `system-0.270` | 511 to 514 | 519 to 523 | 10 of 10 |
| `system-0.320` | 604 to 606 | 611 to 615 | 10 of 10 |
| `system-0.500` | 936 to 938 | 944 to 949 | 10 of 10 |
| `system-0.750` | 1,345 to 1,349 | 1,350 to 1,356 | 10 of 10 |
| `system-0.999` | 1,743 to 1,747 | 1,751 to 1,753 | 10 of 10 |
| `tool-00` | 1,802 to 1,806 | 1,834 to 1,838 | 10 of 10 |
| `tool-04` | 3,003 to 3,009 | 3,388 to 3,392 | 10 of 10 |
| `tool-09` | 3,647 to 3,650 | 4,188 to 4,193 | 10 of 10 |
| `tool-13` | 4,726 to 4,729 | 5,521 to 5,525 | 10 of 10 |
| `user` | 4,860 to 4,865 | 5,636 to 5,643 | 10 of 10 |

A site's range is the nonce: its length in tokens differs from trial to trial.

**Verdict.** Every counted trial of both models matches. By the rule of 0006, `H-M1L1` is `HELD`.

**What it does not show.** One engine build, two models of one size, one machine, one base prefix,
one kind of edit, and one request at a time. One slot is not how this server starts by default; what
the same edits reuse at the defaults is `H-M1LD`, which a later entry states.

**Status.** `H-M1L1` is `[BASELINE]`. `H-M1LD` is `[STRETCH]`: registered, outcome not stated.

### 0008 — 2026-09-29 — Rule 5: what earns [VALIDATED]

prior-entries-sha256: 36c501bf9004b9ba81131d863fbe11dc1350ce9c65d3545f7b480809ec931d94

**Rule for every registration**, added to the four of 0001. Ruled by the operator on 2026-09-29.

5. A result is `[BASELINE]` when it is stated. It becomes `[VALIDATED]` only by a later entry, never
   by an edit, and that entry names the refuter, what it was given to read, the brief it was given,
   what it tried, and what survived. The refuter did not write the code, the records or the entry
   under test, and works from the committed records and requests, the entries and the pinned source,
   and from nothing else. A refuter that finds nothing after a real attempt is stated the same way as
   one that finds something. A replication on another machine, or by another person, is stated in its
   own entry under the same rule.

**Why.** Every check so far was made by the author of the code it checks: the driver, the summarizer,
the stand-in server and the recount were written from one reading of the engine's source, so their
agreement shows consistency, not truth. The header's phrase "an independent attempt to refute it"
needed to say who is independent.

**A check on the instrument, by the author.** It grants nothing under rule 5 and is recorded so that
a refuter can start from it. From the `timings_raw` field of the committed records: the time the
server spent on a prompt against the tokens it says it processed.

| run | ms per processed token | fit | fewest tokens processed | median ms for those | median ms, 4,000 or more |
|---|---|---|---|---|---|
| `20260929T234127Z-qwen-H-M1L1` | 1.50 | 0.995 | 8, in 5 requests | 97 | 7,553 |
| `20260929T235847Z-llama-H-M1L1` | 1.54 | 0.995 | 8, in 5 requests | 97 | 8,922 |
| `20260930T003318Z-qwen-H-M1LD` | 1.51 | 0.996 | 8, in 5 requests | 96 | 7,669 |
| `20260930T005103Z-llama-H-M1LD` | 1.56 | 0.997 | 8, in 5 requests | 97 | 9,097 |
| the four controls runs | 1.56 to 1.60 | 0.9998 or more | 1, in 5 requests each | 41 to 42 | 7,645 to 9,089 |

The fit is the squared correlation of a straight line through each run's requests. A request the
server reports as processed in full took eight to nine seconds; one it reports as reused all but
eight tokens took a tenth of a second, and one reused all but one token, a twenty-fifth. The reuse the
server reports is work it did not do. This is a check that the counter means what the entries take
it to mean; it measures no latency and none of these figures is a result.

**Status.** Rule 5 is in force from this entry. No result is `[VALIDATED]`.

### 0009 — 2026-09-29 — H-M1LD held: at the defaults, an early edit ends the whole prefix

prior-entries-sha256: 2fc80702aead06c8571e662c7c591da13121b53116c84224075f2ca947435807

verdict: H-M1LD = HELD

**Outcome** `[BASELINE]`. The runs registered by 0006 for `H-M1LD` were made at commit `d36bf8c`, on
a server started with no flag but the model. Their records and requests are committed at `76d5d7a`.
Every figure below is from `summarize_m1 --run` on those files, or from the `server` field of the
records.

| | `qwen` | `llama` |
|---|---|---|
| run | `20260930T003318Z-qwen-H-M1LD` | `20260930T005103Z-llama-H-M1LD` |
| outcome | ALL MATCH | ALL MATCH |
| trials counted | 65 | 65 |
| trials matching | 65 | 65 |
| trials not counted | 0 | 0 |
| trials that reused 0 | 15 | 20 |
| trials that reused exactly *d* | 50 | 45 |
| trials that reused anything else | 0 | 0 |
| base request reuse | 0 in 65 of 65 | 0 in 65 of 65 |
| slots, as the server reported | 4 | 4 |
| context, as the server reported | 40,960 | 50,944 |
| *n* | 4,866 to 4,874 | 5,644 to 5,652 |
| fields not reported | None. | None. |

Where each site fell, as *d* / *n*, and what the edited request reused:

| site | `qwen`, share | `qwen`, reused | `llama`, share | `llama`, reused | trials matching |
|---|---|---|---|---|---|
| `system-0.000` | 0.007 to 0.008 | 0 | 0.009 to 0.010 | 0 | 10 of 10 |
| `system-0.100` | 0.044 to 0.045 | 0 | 0.040 | 0 | 10 of 10 |
| `system-0.240` | 0.094 | 0 | 0.083 to 0.084 | 0 | 10 of 10 |
| `system-0.270` | 0.105 to 0.106 | 510 to 516 | 0.092 to 0.093 | 0 | 10 of 10 |
| `system-0.320` | 0.124 | 603 to 606 | 0.109 to 0.110 | 613 to 619 | 10 of 10 |
| `system-0.500` | 0.192 to 0.193 | 936 to 940 | 0.167 to 0.168 | 945 to 951 | 10 of 10 |
| `system-0.750` | 0.276 to 0.277 | 1,343 to 1,349 | 0.239 to 0.240 | 1,352 to 1,354 | 10 of 10 |
| `system-0.999` | 0.358 to 0.359 | 1,744 to 1,750 | 0.310 to 0.311 | 1,748 to 1,755 | 10 of 10 |
| `tool-00` | 0.370 to 0.371 | 1,802 to 1,807 | 0.324 to 0.325 | 1,831 to 1,838 | 10 of 10 |
| `tool-04` | 0.617 | 3,002 to 3,007 | 0.600 | 3,388 to 3,392 | 10 of 10 |
| `tool-09` | 0.749 | 3,647 to 3,651 | 0.742 | 4,190 to 4,195 | 10 of 10 |
| `tool-13` | 0.971 | 4,726 to 4,729 | 0.978 | 5,519 to 5,524 | 10 of 10 |
| `user` | 0.998 | 4,861 to 4,864 | 0.999 | 5,640 to 5,643 | 10 of 10 |

**Verdict.** Every counted trial of both models matches. By the rule of 0006, `H-M1LD` is `HELD`.

**What the runs bracket and do not locate.** The highest share that reused nothing was 0.0945 on
`qwen` and 0.0929 on `llama`; the lowest that reused *d* was 0.1048 and 0.1086. The change happens
between those values, which is consistent with the 0.10 read from the source, and no trial fell
between them. The same site, `system-0.270`, kept its prefix on `qwen` and lost it on `llama`: the
edit is at the same place in the text, and a smaller share of the longer prompt.

**What it does not show.** The limits of 0007, and one more: a request at a time, so no other
conversation held a slot. What the defaults do to a prefix when other requests are being served is
eviction under load, `[FUTURE]`.

**Status.** `H-M1L1` and `H-M1LD` are `[BASELINE]`. The position of an edit is measured on this
engine in both configurations.

### 0010 — 2026-09-29 — 0007 survived a refuter: H-M1L1 is [VALIDATED]

prior-entries-sha256: f399f9db8ee90d744aa5dd8138b4b18f433fa6ecd2378a6ea9c6f503ecfa23ef

**Under rule 5** (entry 0008). The result of 0007 was given to a refuter that did not write the code,
the records or the entry. The operator ruled that one pass is enough.

| | |
|---|---|
| refuter | A separate language-model session running an adversarial brief. It had no access to the session that produced the code and the entries. It is of the same model family as the author, so it is independent of the code and the records, not of the tooling. |
| what it read | An export of commit `76d5d7a`, the whole tree, and llama.cpp at the pinned commit, `tools/server/`. It was denied git, so it could not check the commit hashes 0007 names. It opened the ledger, the configs, the manifest, the records and the requests; it opened nothing under `src/` or `tests/` and imported nothing from the package. |
| the brief | Find a reading of the committed records under which 0007 is wrong. Refute two things separately: that the figures follow from the records, and that the records mean what the entry says. Recompute with your own code. Report what you tried even where it failed. It was pointed at off-by-one in *d*, special tokens, request hashes, nonce reuse, the edit's size and place, exclusions, whether time tracks the counter, whether the reuse could have come from anything but the preceding request, and whether the pinned source contradicts the one-slot account. |
| verdict | Figures: NOT REFUTED. Meaning: NOT REFUTED. "Every figure in entry 0007 recomputed from the records; no sentence found false." |

**What it tried and what survived**, from its report.

| tried | found |
|---|---|
| Every figure of both tables recomputed with its own code. | 130 records, 65 trials, 65 nonces and 130 requests per run; *d* equals the reuse in 65 of 65 per model; the 26 per-site cells and the *n* ranges match; *h* is 27 to 36 and 46 to 54, which 0007 does not state. |
| Whether a site's range is the nonce. | *d* − *h* is one constant per site. Exact. |
| The request files' names. | Each is the sha256 of the body as sent, not of the file. 260 of 260. |
| The edit. | One word became `zebra` in every trial, at the place the site names; `zebra` is in no base prompt. |
| A special token. | Llama's token lists begin with a token the rendered text omits. Harmless: *n*, *d* and the server's counts all include it, and `usage.prompt_tokens` equals the stored count in 130 of 130. |
| Whether the counter is work skipped. | From the pinned source, `cache_n` is the common prefix with the slot's tokens, and only the rest is decoded. From the records, 1.55 to 1.6 ms per processed token; an 8-token request took about 97 ms against 7,600 to 8,900 for its base. |
| Whether the two reuse fields are two measurements. | They are one value reported twice. Agreement between them tests transport, not the count. 0002 and 0006 do not claim otherwise. |
| Whether the reuse came from the preceding request. | In the pinned source the one-slot server clears no idle slot, and the memory cache swaps a prompt in only when it keeps a quarter of it and is strictly better than the slot's, which no request here could be. In the records, each base request's reuse equals its common prefix with the preceding edited prompt, 64 of 64 per run. |
| The strongest counter-case. | A request that is a strict prefix of the held prompt differs from it and would reuse *n* − 1, not *n*. Untested and outside the registered sites; the hypothesis as worded would cover it. 0007's limit "one kind of edit" is what keeps it honest. |

**Consequences.** `H-M1L1` is `[VALIDATED]`. The counter-case is a registered limit: `H-M1L1` speaks
for edits inside the prompt, not for a request that is a prefix of the held one. The agreement of
the two reuse fields is a check on transport and is read as such from here on.

**Status.** `H-M1L1` `[VALIDATED]`; `H-M1LD` `[BASELINE]`, no refuter yet.

### 0011 — 2026-10-01 — 0009 survived a refuter: H-M1LD is [VALIDATED]

prior-entries-sha256: c79383e4d96dcb66d682bc36ca498dd860b85cce2360de3ac9d187b886870ffe

**Under rule 5** (entry 0008). The result of 0009 was given to a second refuter, as independent of the
author as the first: a separate language-model session of the same model family, with no access to
the session that produced the code and the entries, nor to the first refuter's work.

| | |
|---|---|
| what it read | An export of commit `d6e2821`, the whole tree, and llama.cpp at the pinned commit, `tools/server/`. It opened the ledger, the three configs, the manifest, the two records files and the 260 requests; nothing under `src/` or `tests/`; it imported nothing from the package. It was denied git, so it could not check the commit hashes 0009 names. |
| the brief | Find a reading of the committed records under which 0009 is wrong. Refute separately that the figures follow from the records and that the records mean what the entry says. Named attacks: the 0.002 margin, the server's single-precision comparison at the threshold, a reuse that is neither 0 nor *d*, request hashes, nonce reuse, the edit's size, duplicate or missing records, whether the zeros could come from anything but slot assignment, whether the non-zeros could come from the memory cache, whether the pinned source predicts the cliff for a four-slot default server, whether four slots in the records is enough to know the defaults, and whether the bracket is honestly stated. |
| verdict | Figures: NOT REFUTED. Meaning: NOT REFUTED. "Every figure of both tables and the bracket sentence recomputed from the 260 records and 260 stored requests with my own code; no sentence found false." |

**What it tried and what survived**, from its report.

| tried | found |
|---|---|
| Every figure of both tables, with its own code. | All match, including the 26 share cells at three decimals and the two cells nearest a rounding boundary. |
| The bracket. | Highest share at 0 is 0.094456 on `qwen` and 0.092904 on `llama`; lowest at *d* is 0.104766 and 0.108572; nothing between. |
| The margin and the server's arithmetic. | The closest trial is 0.0048 from the threshold; an emulation of the server's single-precision comparison disagrees with the entry in 0 trials. |
| The edit and the records. | One word became `zebra` in every trial; no nonce repeats within or across the two runs; sequence numbers run 1 to 130 with no gap; every recorded prediction equals its recomputation. |
| Whether the zeros are real. | An edited request that reused 0 took about as long as its base (medians 7,660 against 7,677 ms on `qwen`, 9,102 against 9,105 on `llama`); one that reused *d* scales with the tokens processed. The requests were strictly sequential, at most 0.08 s apart, so no restart intervened. |
| Whether the source predicts the cliff. | Yes, and it found more: the edited request meets the base's slot intact, so a reuse of 0 needs the slot the least-recently-used choice lands on to be already empty. That happens only with idle-slot clearing, which the server enables only when the slot count is automatic. |
| Whether the records can tell the defaults from a four-slot flag. | They can, more than 0006 allowed: every base request that followed another request reused 0 (64 of 64 per model), where a server with four slots and no shared buffer would have kept the previous prompt and reused its template head, as the one-slot runs did (0004: 4 to 7 and 31 to 33 tokens). The non-round context of 50,944 on `llama` is consistent with no context flag. |
| The strongest counter-case. | The hypothesis names 0.10; the data hold equally for any threshold between 0.0945 and 0.1048. The entry says exactly this. |

**Consequences.** `H-M1LD` is `[VALIDATED]`. The limit in 0006 that the records cannot tell the
defaults from a four-slot flag is withdrawn for these two runs: a base request's reuse of 0, where a
held slot would have reused the shared head, is evidence that idle slots were cleared.

**Status.** `H-M1L1` and `H-M1LD` are `[VALIDATED]`. The position of an edit is measured and refuted
without result on this engine in both configurations. No other cause is designed.

### 0012 — 2026-10-01 — Eviction by intervening requests registered on llama.cpp: H-M7LD

prior-entries-sha256: b8be788427ed94be2f83cfd0fba86db602876fb4fab892acfdc2d23997503387

**Registers** `config/m7.toml`, now `registered_by = "0012"`, and one hypothesis. Engine, models and
machine are those of 0002, the server at its defaults as under `H-M1LD`, the request parameters
those of `config/controls.toml`.

**Id.** `M7` is the seventh cause of 0001, `D` the defaults as in 0006. Ruled by the operator on
2026-10-01: one hypothesis, at the defaults only; the one-slot configuration is named below as not
measured.

| id | server | the records must say | predicted reuse of the resend |
|---|---|---|---|
| `H-M7LD` | Started with no flag but the model. | 4 slots, and a slot context that every request fits. | *n* − 1 when the states of the anchor and of the first *K* − 1 foreign prompts fit together in 8192 MiB, and 0 otherwise. |

A prompt's state is its token count times the bytes one token's keys and values take: layers × 2 ×
KV heads × head width × 2 bytes, read from each model file's header on 2026-10-01 and fixed in the
config (Qwen3-8B 36 × 2 × 8 × 128 × 2 = 147,456; Llama-3.1-8B 32 × 2 × 8 × 128 × 2 = 131,072). The
8192 MiB is the server's `--cache-ram` at its default (`common/arg.cpp` at the pin). The *K*-th
foreign prompt is still in its slot when the resend arrives, so it is not counted.

**The reading**, continuing 0005 (`tools/server/server-context.cpp` and `server-task.cpp` at the
pin). At the defaults a slot's prompt is saved to the RAM prompt cache and the slot cleared when a
request launches elsewhere. The cache keeps entries in arrival order and, before adding one, drops
the oldest until the new one fits under its size limit. A request restores a cached prompt when it
shares at least a quarter of it. So the anchor's copy outlives *K* − 1 foreign prompts if they fit
beside it, and its resend then reuses *n* − 1, the identical-resend rule of 0003; otherwise the copy
is gone and the resend reuses 0. The source has a second pass over a token total; for these prompts it
binds at the same *K* as the size rule. The records carry the slot context that pass uses, and
`summarize_m7` reports per trial which pass would have bound. Only the size rule predicts.

**A trial** is *K* + 2 requests under *K* + 1 fresh nonces: an anchor (the base request), *K* foreign
requests (the base request, each under its own nonce) served one at a time, then the anchor's bytes
again. *K* runs over 0, 1, 4, 8, 10, 11, 12, 13 and 16, three times each: 27 trials and 279 requests
per model. The anchor and every foreign request are controls inside the trial: at the defaults a
fresh prompt reuses 0 (0003, 0009).

**What decides.**

| case | rule |
|---|---|
| A trial matches. | The resend's reuse equals its prediction, and every request's two counts add up to *n* and its two reuse fields agree. |
| `HELD` | Every counted trial of both models matches. |
| `NOT CONFIRMED` | At least one counted trial does not match. The results entry states, per model, the largest *K* whose resend reused *n* − 1 and the smallest whose resend reused 0. |
| A control fails. | The anchor or a foreign request reuses anything but 0; the resend is not the anchor's bytes; a nonce repeats. The run stops, and no verdict follows from it. |
| NOT MEASURABLE | The server does not report a field, or no slot context; a request has at least as many tokens as the slot context, which the server refuses; the local date changed inside a trial, which a template may carry. The verdict stays `unresolved`. |
| The records say another number of slots, or more than one slot context. | The run is not that experiment. |

A prediction is a function of the stored token counts and the two registered constants, and of
nothing else. The driver writes it before the resend is sent; `summarize_m7` recomputes it from the
stored tokens and refuses a record that carries another value.

**Known before the run.**

| fact | consequence |
|---|---|
| The server's properties do not report the cache size. | The run is started with no flag but the model; 8192 MiB is read, not recorded. A cliff elsewhere than predicted is a result about that reading. |
| Four slots in the records are read as the defaults (0011), and the slot context is recorded. | What 0006 could not tell, these records can. |
| The server's own logs of the four runs of 0007 and 0009, read on 2026-10-01 (not committed artifacts), show the cache at its limit, dropping entries of 684 to 686 MiB on `qwen` and 705 to 707 MiB on `llama`, and the runs complete. | The sizes agree with the constants above. The cache size is not changed. A limit the server lowers under memory pressure would show as an early cliff and be reported. |
| Unrecorded requests of this kind were sent to the `qwen` server before this entry, at *K* = 1 and *K* = 12. | Nothing from them is evidence and no figure from them appears here. The rule and the schedule are those committed at `51ad5c7`, before that contact. |
| Not measured: the one-slot configuration, where the source reads the cliff one request earlier because the slot's prompt is saved before the cache is searched; and requests in flight at the same time. | The statement says "served between them, one at a time". |

**Status.** `H-M7LD` is `[STRETCH]`: registered, not run. `qwen` runs first.

### 0013 — 2026-10-02 — H-M7LD held: the twelfth intervening prompt ends the prefix

prior-entries-sha256: b326c4d10f9ffe72f4282b6e41ff3087099a9ff396b585753b76c012633a7fe5

verdict: H-M7LD = HELD

**Outcome** `[BASELINE]`. The runs registered by 0012 were made at commit `c4dbe6f`, on a server
started with no flag but the model, one after the other on the same day. Their records and requests
are committed at `8511098`. Every figure below is from `summarize_m7 --run` on those files, or from
the `server` field of the records.

| | `qwen` | `llama` |
|---|---|---|
| run | `20261002T143151Z-qwen-H-M7LD` | `20261002T151650Z-llama-H-M7LD` |
| outcome | ALL MATCH | ALL MATCH |
| trials counted | 27 | 27 |
| trials matching | 27 | 27 |
| resend reused *n* − 1 | at *K* = 0, 1, 4, 8, 10, 11; 18 of 18 | the same, 18 of 18 |
| resend reused 0 | at *K* = 12, 13, 16; 9 of 9 | the same, 9 of 9 |
| resend reused anything else | 0 | 0 |
| anchor and foreign requests | 0 in 252 of 252 | 0 in 252 of 252 |
| largest *K* kept, smallest *K* lost | 11, 12 | 11, 12 |
| slots, as the server reported | 4 | 4 |
| context, as the server reported | 40,960 | 50,944 |
| *n*, over all 279 requests | 4,864 to 4,873 | 5,641 to 5,652 |
| bytes per token, registered | 147,456 | 131,072 |
| fields not reported | None. | None. |

The modelled cache at each *K*, as the anchor's state plus the first *K* − 1 foreign states, against
the 8,192 MiB limit:

| *K* | `qwen`, MiB | `llama`, MiB | fits | predicted | reused, both models, 3 of 3 |
|---|---|---|---|---|---|
| 0 | 685 | 706 | yes | *n* − 1 | *n* − 1 |
| 1 | 684 to 685 | 706 | yes | *n* − 1 | *n* − 1 |
| 4 | 2,738 to 2,739 | 2,823 to 2,824 | yes | *n* − 1 | *n* − 1 |
| 8 | 5,477 to 5,478 | 5,646 to 5,647 | yes | *n* − 1 | *n* − 1 |
| 10 | 6,847 to 6,848 | 7,058 to 7,059 | yes | *n* − 1 | *n* − 1 |
| 11 | 7,531 to 7,532 | 7,764 to 7,765 | yes | *n* − 1 | *n* − 1 |
| 12 | 8,216 to 8,218 | 8,470 to 8,472 | no | 0 | 0 |
| 13 | 8,900 to 8,903 | 9,174 to 9,178 | no | 0 | 0 |
| 16 | 10,954 to 10,955 | 11,292 to 11,294 | no | 0 | 0 |

**Verdict.** Every counted trial of both models matches. By the rule of 0012, `H-M7LD` is `HELD`.

**What the runs bracket and do not locate.** The resend kept its whole prefix after eleven
intervening prompts and lost all of it after twelve, on both models; no *K* between 11 and 12 exists,
so the cliff is located to the request. Where it falls in bytes is bracketed: the cache held 7,532 MiB
and refused 8,216 on `qwen`, held 7,765 and refused 8,470 on `llama`, which is consistent with the
8,192 MiB read from the source and not a measurement of it. The source's second eviction pass, on a
token total against the recorded context, would have evicted at exactly the same trials as the size
rule in 54 of 54; nothing here tells the two passes apart.

**What it does not show.** Requests were served one at a time; what the defaults do to a prefix while
other requests are in flight is not measured. The one-slot configuration is not measured: the source
reads it to lose the prefix one request earlier, because the slot's prompt is saved before the cache
is searched. The eviction is of a prompt of about 4,870 or 5,650 tokens by prompts of the same size;
a different mix of sizes moves the count, not the rule. The cache size is read, not recorded: the
server's properties do not report it.

**Status.** `H-M7LD` is `[BASELINE]`, no refuter yet. Two causes are measured on this engine: the
position of an edit (0007, 0009) and eviction by intervening requests. Six remain `[FUTURE]`.

### 0014 — 2026-10-02 — 0013 survived a refuter: H-M7LD is [VALIDATED]

prior-entries-sha256: a864997323fc4851a66b2d18fcbd64cb58f075bc9e6dc0f1f366d40c4fb9a237

**Under rule 5** (entry 0008). The result of 0013 was given to a third refuter, independent of the
author in the same way as those of 0010 and 0011: a separate language-model session of the same model
family, with no access to the session that produced the code and the entries, nor to the earlier
refuters' work.

| | |
|---|---|
| what it read | An export of commit `921c3fc`, the whole tree, and llama.cpp at the pinned commit: `tools/server/`, `common/`, `src/llama-context.cpp`, `src/llama-kv-cache.cpp`, `src/llama-kv-cells.h`. It opened the ledger, the three configs, the manifest, the two record files and the 558 stored requests; nothing under `src/` or `tests/`; it imported nothing from the package. It was denied git, so it could not check the commit hashes 0013 names. |
| the brief | Find a reading of the committed records under which 0013 is wrong. Refute separately that the figures follow from the records and that the records mean what the entry says. Named attacks: missing, duplicated or disordered records; a resend whose bytes or nonce differ from its anchor's; nonce reuse; a foreign request that is not the base request; the "first *K* − 1" accounting; the recorded prediction against a recomputation; the date inside a trial; the three reuse fields and the counts; another mechanism for a 0 at *K* ≥ 12 (slot choice, the 0.25 restore rule, the similarity threshold, a restart, a shrunk cache); whether *n* − 1 at *K* ≤ 11 could come from the slot rather than the cache; whether the source evicts in arrival order; whether the state blob exceeds tokens × bytes enough to move the *K*; whether the bracket over- or under-claims; whether any field records the cache size. |
| verdict | Figures: NOT REFUTED. Meaning: NOT REFUTED. "Every figure recomputed from the 558 records and 558 stored requests matches; the pinned source evicts in arrival order at save time, saves and clears idle slots at the defaults, and 'first *K* − 1' follows from save-after-launch." |

**What it tried and what survived**, from its report.

| tried | found |
|---|---|
| Every figure of both tables, with its own code. | All match; the recorded prediction fields equal its recomputation in 54 of 54 resends. |
| The records' shape. | Sequence 1 to 279 in each run, no overlapping timestamps, one local date; the resend's bytes, hash and nonce equal its anchor's in 27 of 27; every foreign body equals the anchor's apart from the nonce, 252 of 252; no nonce repeats within or across runs. |
| Whether the zeros are real. | A resend that reused *n* − 1 processed its prompt in 41 to 77 ms; every other request took 7.6 to 9.3 s. No gap between consecutive requests exceeds 0.31 s, so no restart intervened. A shrunk cache or a failed restore would have had to coincide in 6 of 6 trials at *K* = 12 on two models. |
| Whether *n* − 1 at *K* ≥ 1 could come from the slot. | No: after each launch every idle slot is saved and, with a shared buffer, cleared (`server-context.cpp` 2447–2460), so the anchor's slot is empty and cannot be chosen by similarity; the only path to reuse is the cache restore. |
| Whether the records pin the defaults. | The recorded slot context equals the pool (40,960 is Qwen3's training context); without a shared buffer it would be the pool divided by four (`llama-context.cpp` 291–295). Unified KV is thereby inferred from the records, not from the flag's absence. |
| The "first *K* − 1" accounting and arrival order. | Each foreign prompt is saved at the next launch; the resend's restore precedes its own launch's saves; `alloc` and `update` pop the front while over the limit (`server-task.cpp` 1750–1757, 1871–1876). Residue of earlier trials sits ahead of the anchor and goes first. |
| Whether the state blob is bigger than tokens × bytes. | By about 0.7 MiB at *K* = 12: 12 bytes of metadata per cell and per-layer headers, no checkpoints for these models. The *K* and the bracket do not move. |
| Whether anything records the cache size. | Nothing: `/props` carries no cache-size key. |

**Two limits it added**, kept on record. The source's token pass cannot evict anything the size pass
has not, when a size limit is set: 0013's "54 of 54" is true and says less than it reads. And the
title's count is exact for prompts of this size: the eviction fires when the eleventh foreign state is
saved at the twelfth's launch.

**Consequences.** `H-M7LD` is `[VALIDATED]`. The reading that a four-slot record is the defaults
(0011) gains a second leg: the recorded slot context is the whole pool, which only a shared buffer
gives.

**Status.** `H-M1L1`, `H-M1LD` and `H-M7LD` are `[VALIDATED]`. Two causes are measured and refuted
without result on this engine; six remain `[FUTURE]`.

### 0015 — 2026-10-02 — Serialization drift and templating registered on llama.cpp: H-M2L1, H-M3L1, H-M3LD

prior-entries-sha256: e747030301fe45acfa3d4f64ec79036bc0d8f5d5e23c6cc6be897096e9a8e86f

**Registers** `config/m2.toml` and `config/m3.toml`, now `registered_by = "0015"`, and three
hypotheses, each with its own verdict cell. Engine, models and machine are those of 0002; the request
parameters those of `config/controls.toml`; the server configurations those of 0006, one slot
(`--parallel 1`) and the defaults.

**Ids.** `M2` and `M3` are the second and third causes of 0001; the configuration character is as in
0006. Ruled by the operator on 2026-10-02: the two causes share one registering entry because they
share one build; serialization drift is registered on one slot only, its prediction at the defaults
following from `H-M1LD`; templating is registered in both configurations.

| id | server | the records must say | predicted reuse of the changed request |
|---|---|---|---|
| `H-M2L1` | Started with `--parallel 1`. | 1 slot. | *d*; *n* − 1 when the two renders are identical. |
| `H-M3L1` | Started with `--parallel 1`. | 1 slot. | *d*; *n* − 1 when the two renders are identical. |
| `H-M3LD` | Started with no flag but the model. | 4 slots. | *d* when *d* / *n* is above 0.10, and 0 otherwise; *n* − 1 when the renders are identical. |

*d* is the number of leading tokens the base prompt and the changed prompt have in common, under the
server's own tokenizer, each prompt as the server renders it; *n* is the token count of the changed
prompt. Identical renders make the changed request a byte-identical resend of the prompt, which this
engine reuses to *n* − 1 (0003); the prediction says so, in one place, for both experiments.

**The reading**, continuing 0005 (`common/chat.cpp`, `tools/server/server-common.cpp`, and the two
models' chat templates read from their files, all at the pin). The server parses a request into a
type that keeps object key order and discards whitespace; it then parses each tool into three fields,
`name`, `description` (empty if absent) and `parameters` (kept as text and re-parsed), and rebuilds
the object the template sees as `type`, `function`, `name`, `description`, `parameters`, dropping any
other key. Only the key order *inside* `parameters`, and the order of the tools, reach the template.
A request's `chat_template_kwargs` are merged after the server's own template context, so a request
may set `date_string`, which Llama 3.1's template prints at the head of the system block (the server
otherwise supplies the local date) and Qwen3's template does not use, and `enable_thinking`, which
Qwen3's template reads for the generation prompt at the tail and Llama 3.1's does not read.

**Serialization drift: a trial** is two requests under one fresh nonce: the base request, then the
same request with its `tools` array written differently, one of six registered changes. The change
is to the request's bytes; each carries the reading of what the render will do, which the summarizer
reports against the render and which decides nothing.

| change | what is written differently | reading |
|---|---|---|
| `S1` | indentation and spacing only | identical render |
| `S2` | `type` and `function` swapped at the top of tool 4 | identical render |
| `S3` | tools 0 and 1 swapped | differs at tool 0 |
| `S4` | the keys of `properties` reversed inside tool 10's parameters | differs inside tool 10 |
| `S5` | `description` after `parameters` in every tool | identical render |
| `S6` | an unknown key on every tool's `function` | identical render |

Each change is tried 5 times: 30 trials and 60 requests per model.

**Templating: a trial** is two requests under one fresh nonce whose messages and tools are the same
bytes. Every request carries `chat_template_kwargs` `{"date_string": "01 Oct 2026", "enable_thinking": true}`;
the changed request replaces one value: `T1` sets `date_string` to `02 Oct 2026`, `T2` sets
`enable_thinking` to false. Each change is tried 5 times per configuration: 10 trials and 20 requests
per model and configuration. The fixed date keeps the run independent of the clock; the entry that
decides states what the server would print without it.

**What decides.**

| case | rule |
|---|---|
| A trial matches. | The changed request's reuse equals its prediction, both requests' counts add up to *n*, and their two reuse fields agree. |
| `HELD` | Every counted trial of both models matches. |
| `NOT CONFIRMED` | At least one counted trial does not match. The results entry states the prediction and the reuse of every trial. |
| A trial is not counted. | Its *d* / *n* lies within 0.002 of 0.10, under `H-M3LD` only. It is reported. |
| A control fails. | The base request reuses more than *h*, the tokens that start before the end of the nonce; the two bodies differ in anything but the `tools` text (`H-M2L1`) or the `chat_template_kwargs` (`H-M3L1`, `H-M3LD`). The run stops, and no verdict follows from it. |
| NOT MEASURABLE | The server does not report a field. The verdict stays `unresolved`. |
| The records say another number of slots. | The run is not that experiment. |

A prediction is a function of the two stored prompts and the rule above, and of nothing else. The
driver writes it before the changed request is sent; `summarize_m2` and `summarize_m3` recompute it
from the stored tokens and refuse a record that carries another value.

**Known before the run.**

| fact | consequence |
|---|---|
| The readings of `S1` to `S6` are readings of source. | A render that disagrees with a reading is reported as such and changes no outcome; the prediction is from the render. |
| Llama 3.1's template puts the tools in the first user message, after the nonce, unless `tools_in_user_message` is false; then it puts them before the system text, ahead of the nonce, and consecutive trials share a head of about 0.7 of the prompt. | This experiment does not set that argument, so the nonce leads every prompt as in 0002 to 0013. The argument is reserved for an experiment that must render a conversation without a user turn. |
| Unrecorded requests of these kinds were sent to both models before this entry, on one slot and at the defaults. | Nothing from them is evidence and no figure from them appears here. The changes, the arguments and the rules are those committed at `3c95d80` and in this entry's commit. |

**Status.** `H-M2L1`, `H-M3L1` and `H-M3LD` are `[STRETCH]`: registered, not run. Order: `H-M2L1`
on `qwen` then `llama`; `H-M3L1` on both; `H-M3LD` on both.

### 0016 — 2026-10-02 — H-M2L1 held: the server normalises a tool's shape and keeps its order

prior-entries-sha256: 4e499f82f59a7e62a8cf0a4f2dc42c3879ebc5413e330ad2040f9d16a0dc77b4

verdict: H-M2L1 = HELD

**Outcome** `[BASELINE]`. The runs registered by 0015 for `H-M2L1` were made at commit `649864b`, on
a server started with `--parallel 1`. Their records and requests are committed at `019a041`. Every
figure below is from `summarize_m2 --run` on those files, or from the `server` field of the records.

| | `qwen` | `llama` |
|---|---|---|
| run | `20261002T202530Z-qwen-H-M2L1` | `20261002T203125Z-llama-H-M2L1` |
| outcome | ALL MATCH | ALL MATCH |
| trials counted | 30 | 30 |
| trials matching | 30 | 30 |
| readings disagreeing with the render | 0 | 0 |
| base request reuse | 0 to 6, within *h* of 28 to 36 | 0 to 32, within *h* of 46 to 52 |
| slots, as the server reported | 1 | 1 |
| context, as the server reported | 40,960 | 50,944 |
| *n*, over all 60 requests | 4,864 to 4,872 | 5,643 to 5,649 |
| fields not reported | None. | None. |

What each re-serialization did to the render, and what the changed request reused:

| change | render | `qwen`, *d* / *n* | `qwen`, reused | `llama`, *d* / *n* | `llama`, reused | trials matching |
|---|---|---|---|---|---|---|
| `S1` spacing only | identical | 1.000 | *n* − 1 | 1.000 | *n* − 1 | 10 of 10 |
| `S2` `type`/`function` swapped, tool 4 | identical | 1.000 | *n* − 1 | 1.000 | *n* − 1 | 10 of 10 |
| `S3` tools 0 and 1 swapped | differs at character 8,293 / 8,578 | 0.368 to 0.369 | 1,792 to 1,798 | 0.323 to 0.324 | 1,825 to 1,827 | 10 of 10 |
| `S4` `properties` reversed, tool 10 | differs at character 15,740 / 22,753 | 0.779 | 3,790 to 3,794 | 0.774 | 4,365 to 4,371 | 10 of 10 |
| `S5` `description` after `parameters` | identical | 1.000 | *n* − 1 | 1.000 | *n* − 1 | 10 of 10 |
| `S6` unknown key on `function` | identical | 1.000 | *n* − 1 | 1.000 | *n* − 1 | 10 of 10 |

**Verdict.** Every counted trial of both models matches. By the rule of 0015, `H-M2L1` is `HELD`.

**What it shows.** The engine's parser, read in 0015, does what was read: a client may re-indent its
JSON, reorder the keys of a tool or of its `function`, or carry extra keys there, and the rendered
prompt does not change, so the prefix lives; a client that reorders its tools, or the keys inside a
tool's `parameters`, changes the render from that point and the prefix ends there. The position is
exactly where the render first differs, on both models, in 20 of 20 such trials.

**What it does not show.** The defaults are not run: every kept change here lands at 0.32 of the
prompt or later, far above 0.10, so `H-M1LD` says the defaults reuse the same *d*. Other engines'
parsers, and re-serializations of the messages rather than the tools, are not measured.

**Status.** `H-M2L1` is `[BASELINE]`, no refuter yet.

### 0017 — 2026-10-02 — H-M3L1 and H-M3LD held: a template argument ends the prefix where the template prints it

prior-entries-sha256: 517d07784a0f699b4ad38116631cf411f819874b35f37347733beb80359da24a

verdict: H-M3L1 = HELD
verdict: H-M3LD = HELD

**Outcome** `[BASELINE]`. The runs registered by 0015 for `H-M3L1` and `H-M3LD` were made at commit
`649864b`, on a server started with `--parallel 1` and on one started with no flag but the model.
Their records and requests are committed at `019a041`. Every figure below is from `summarize_m3 --run`
on those files, or from the `server` field of the records.

| | `qwen`, one slot | `llama`, one slot | `qwen`, defaults | `llama`, defaults |
|---|---|---|---|---|
| run | `20261002T203754Z-qwen-H-M3L1` | `20261002T203948Z-llama-H-M3L1` | `20261002T204246Z-qwen-H-M3LD` | `20261002T204441Z-llama-H-M3LD` |
| outcome | ALL MATCH | ALL MATCH | ALL MATCH | ALL MATCH |
| trials counted / matching | 10 / 10 | 10 / 10 | 10 / 10 | 10 / 10 |
| trials not counted | 0 | 0 | 0 | 0 |
| base request reuse | 0 to 5, within *h* | 0 to 32, within *h* | 0 | 0 |
| slots, as the server reported | 1 | 1 | 4 | 4 |
| context, as the server reported | 40,960 | 50,944 | 40,960 | 50,944 |
| *n*, over all 20 requests | 4,867 to 4,875 | 5,643 to 5,651 | 4,867 to 4,876 | 5,645 to 5,652 |
| fields not reported | None. | None. | None. | None. |

What each argument did to the render, and what the changed request reused:

| change | model | render | *d* | *d* / *n* | reused, one slot | reused, defaults |
|---|---|---|---|---|---|---|
| `T1` date | `qwen` | identical | *n* | 1.000 | *n* − 1 | *n* − 1 |
| `T1` date | `llama` | differs at character 116 | 24 | 0.0042 to 0.0043 | 24 | 0 |
| `T2` thinking off | `qwen` | differs at character 19,691 | *n* − 4 | 0.9992 | *n* − 4 | *n* − 4 |
| `T2` thinking off | `llama` | identical | *n* | 1.000 | *n* − 1 | *n* − 1 |

Each row is 5 of 5 trials in each configuration.

**Verdict.** Every counted trial of both models matches in both configurations. By the rule of 0015,
`H-M3L1` and `H-M3LD` are `HELD`.

**What it shows.** On Llama 3.1 the date is the 24th token of the prompt, before anything the client
sent. A change to it keeps 24 tokens with one slot and nothing at the defaults, where 0.004 of the
prompt is under the 0.10 the engine needs to choose the slot. The runs fixed the date by argument so
that they would not depend on the clock; without the argument the server prints the local date, so on
this model at the defaults every cached prefix ends at local midnight with no change by the client,
the limit 0009 named and this entry measures through the argument that stands in for the clock. On
Qwen3 the date argument changes nothing. Turning thinking off on Qwen3 changes the last four tokens
of the render, after the user message, and keeps everything before them in both configurations; on
Llama 3.1 it changes nothing.

**What it does not show.** The rollover itself (two requests across a real midnight) is not measured;
the argument is. Other template arguments, and other templates, are not measured. The one argument
0015 names and does not set, `tools_in_user_message`, is not measured here.

**Status.** `H-M3L1` and `H-M3LD` are `[BASELINE]`, no refuter yet. Four causes are measured on this
engine: the position of an edit, eviction by intervening requests, serialization drift and
templating. Four remain `[FUTURE]`: idle expiry, rebuild, model switch, lifespan on recorded runs.

### 0018 — 2026-10-02 — 0016 and 0017 survived a refuter: H-M2L1, H-M3L1 and H-M3LD are [VALIDATED]

prior-entries-sha256: a5ea49a29c37ef950810e49ea928a6f6ca0a055fbdb8686fa9f9524b2a0b046d

**Under rule 5** (entry 0008). The results of 0016 and 0017 were given together to a fourth refuter,
independent of the author in the same way as those of 0010, 0011 and 0014: a separate language-model
session of the same model family, with no access to the session that produced the code and the
entries, nor to the earlier refuters' work.

| | |
|---|---|
| what it read | An export of commit `db0ee11`, the whole tree, and llama.cpp at the pinned commit: `common/chat.cpp`, `common/json.h`, `common/json.cpp`, `common/common.h`, `common/arg.cpp`, `tools/server/server-common.cpp`, `server-context.cpp`, `server-task.cpp`; Qwen3-8B's chat template from its public model card. It opened the ledger, the four configs, the manifest, the six record files and every stored request they name (200), checking each body against its own hash; nothing under `src/` or `tests/`; it imported nothing from the package. It was denied git, so it could not check the commit hashes the entries name. |
| the brief | For each entry separately, find a reading of the committed records under which it is wrong: the figures (recompute *d* and the render difference from the stored tokens and renders; the recorded predictions against the rules of 0015 including the *n* − 1 correction for identical renders; nonces; counts and fields; bodies differing in nothing but the tools text or the one named argument) and the meaning (the parser rebuild in source and in the renders; the merge order of the template arguments; the Llama date's position; the Qwen tail; whether *n* − 1 could come from anything but the held slot and 0 from anything but the 0.10 rule; whether the sentence about local midnight overreaches; timings as an independent check). |
| verdict | 0016: figures NOT REFUTED, meaning NOT REFUTED. 0017: figures NOT REFUTED, meaning NOT REFUTED. |

**What it tried and what survived**, from its report.

| tried | found |
|---|---|
| Every figure of both entries, with its own code. | All match: 30 of 30 and 10 of 10 per cell; every recorded prediction equals its recomputation; every count adds up and the three reuse fields agree; each of the 100 nonces belongs to exactly one trial; each pair's bodies differ in nothing but the tools text (0016) or the one named argument (0017). |
| Whether the readings of 0015 describe the renders. | `S1` parses equal; `S2` and `S5` parse equal only when key order is ignored; `S6` parses differently, and its key appears in no render. The renders show the rebuilt order for all three. |
| Whether the zeros and the *n* − 1 are real. | A request that reused *n* − 1 processed its prompt in 40 to 53 ms; one that reused 0 or 24 took 8.9 to 9.2 s; `S3` 5.2 to 6.5 s, `S4` 2.1 to 2.4 s. |
| The source behind each reading. | The parser reads only `name`, `description`, `parameters` and rebuilds the tool (`common/chat.cpp` 558–608); the JSON type keeps key order (`common/json.cpp` 14); the template arguments overwrite the server's context after it is built (`chat.cpp` 1293–1296) and a request's override the command line's (`server-common.cpp` 1332–1336); the date comes from the local clock (`chat.cpp` 36–43, 1080–1087); a slot is chosen only above 0.10 (`server-context.cpp` 1601, default at `common/common.h` 696); an identical resend is counted *n* − 1 (3413–3416). |
| Whether the override is visible in the records. | Every record carries `local_date` 2026-10-02 while every base render prints `01 Oct 2026`. |
| Where the Llama date sits. | Token pieces 0 to 23 are the header, piece 24 is `01`, the only token that changes; the nonce starts at piece 30. |
| What the Qwen thinking switch does. | The base render is a strict prefix of the changed render: four pieces are appended, `<think>`, a blank line, `</think>`, a blank line, and nothing before them changes. |
| The sentence about local midnight. | Supported by the source and by the argument, which stands in for the same template variable. For a prompt under about 240 tokens the date's share would exceed 0.10, the slot would be chosen and 24 tokens kept. |

**Four precisions it added**, kept on record. 0017's "changes the last four tokens" should read
"appends four tokens after the generation prompt": the base render is a prefix of the changed one.
"The 24th token" counts from zero, as the character positions in these entries do; counted from one
it is the 25th, and the date spans five tokens. 0016 measured an extra key on a tool's `function`
only; the source drops an extra key at the top of a tool as well, and that is read, not measured.
The local-midnight sentence holds for prompts of this size; a prompt short enough for the date to be
a tenth of it would keep the 24 tokens.

**Consequences.** `H-M2L1`, `H-M3L1` and `H-M3LD` are `[VALIDATED]`.

**Status.** Six hypotheses on this engine, all `[VALIDATED]`: `H-M1L1`, `H-M1LD`, `H-M7LD`,
`H-M2L1`, `H-M3L1`, `H-M3LD`. Four causes are measured and refuted without result; four remain
`[FUTURE]`.

### 0019 — 2026-10-06 — Idle expiry registered on llama.cpp: H-M4LD, H-M4LS

prior-entries-sha256: d42d58370f266a620666c5b0f62ce348c66658bba62430a0676d0521b74a5d93

**Registers** `config/m4.toml`, now `registered_by = "0019"`, and two hypotheses. Engine, models and
machine are those of 0002, the request parameters those of `config/controls.toml`.

**Id.** `M4` is the fourth cause of 0001, idle expiry; `D` the defaults as in 0006; `S` a server
started with its idle timer on. Ruled by the operator on 2026-10-03 and 2026-10-06: idle expiry is
read as time alone, with the server's one timer as the engine event that depends on it; the gaps are
taken from recorded agent runs, so the corpus was vendored first.

| id | server | the records must say | predicted reuse of the resend after a gap of *g* seconds |
|---|---|---|---|
| `H-M4LD` | Started with no flag but the model. | 4 slots, a slot context every request fits, and `is_sleeping` false after every gap. | *n* − 1 at every registered *g*: 0, 2, 4, 60 and 600. |
| `H-M4LS` | Started with `--sleep-idle-seconds 60` and nothing else. | 4 slots, a slot context every request fits, `is_sleeping` false after a gap of 20 and true after a gap of 100. | *n* − 1 at *g* = 20; 0 at *g* = 100. |

**The reading** (`tools/server/server-queue.cpp` and `server-context.cpp` at the pin). The server has
one timer. Its loop notes the time of the last task posted, moved forward by the time the slots took,
and once a second compares the idle time with `--sleep-idle-seconds`; at −1, the default, it never
sleeps. A slot's last-used time serves only the choice of slot, and the prompt cache has no age.
Entering sleep frees the contexts, and with them every slot; the reload that follows creates a new,
empty prompt cache. With nothing served between an anchor and its resend the anchor's slot keeps its
prompt (0005: a slot is cleared when another request launches), so at the defaults the resend is an
identical resend into a held slot, *n* − 1 (0003), at any *g*. `GET /props` posts no task: it neither
moves the timer nor wakes the server, and it reports `is_sleeping`. `POST /apply-template` and
`POST /tokenize` post no task either, but they wait for a sleeping server to reload; so the driver
renders and tokenizes the anchor before sending it, and sends nothing but one `GET /props`, at the
end of the gap, until the resend is answered.

**The gaps.** `corpus/recorded/tau2-airline-claude-3-7-sonnet/` holds fifty of tau2-bench's published
airline conversations (one trial per task; provenance in the folder). `prefix_mortality.recorded
stats` reads, from their timestamps, the span from an assistant message to the next message of the
conversation, which is when the agent's next request leaves and so the time the serving side holds
that conversation's prefix with nothing arriving: 0.0 s at the median, 1.5 s at the 90th percentile,
3.9 s at most, over 762 assistant turns. The registered gaps at the defaults are 0 (identity), 2 and 4
(the 90th percentile and the maximum of that span, rounded up), 60 (the threshold the `S` cell
uses, measured here with no timer), and 600 (a bound ten minutes beyond anything in the corpus).

**A trial** is two requests under one fresh nonce: the anchor (the base request), a gap of *g*
seconds, one `GET /props` whose `is_sleeping` the resend's record carries, then the anchor's bytes
again. `H-M4LD`: *g* over 0, 2, 4, 60 and 600 seconds, twice each: 10 trials and 20 requests per
model, about 25 minutes. `H-M4LS`: *g* over 20 and 100 seconds, three times each: 6 trials and 12
requests per model, about 8 minutes and three reloads. The anchor is a control inside the trial: a
fresh prompt reuses 0 (0003, 0009). A registered gap keeps at least 5 seconds from the threshold, for
the once-a-second check; the recorded gap, from the anchor's last timestamp to the resend's first,
must be at least *g* and less than *g* + 5.

**What decides.**

| case | rule |
|---|---|
| A trial matches. | The resend's reuse equals its prediction, and every request's two counts add up to *n* and its two reuse fields agree. |
| `HELD` | Every counted trial of both models matches. Each hypothesis is decided on its own runs. |
| `NOT CONFIRMED` | At least one counted trial does not match. The results entry states, per model and per gap, how many resends reused *n* − 1 and how many 0. |
| A control fails. | The anchor reuses anything but 0; the resend is not the anchor's bytes; a record lies between them; the recorded gap is below *g* or at least *g* + 5; `is_sleeping` after the gap disagrees with the prediction (the server did not do what its flag says). The run stops, and no verdict follows from it. |
| NOT MEASURABLE | The server does not report a field, a slot context or `is_sleeping`; a request has at least as many tokens as the slot context; the local date changed inside a trial. The verdict stays `unresolved`. |
| The records say another number of slots, more than one slot context, or a gap not registered. | The run is not that experiment. |

A prediction is a function of the registered timer, the registered gap and the anchor's token count,
and of nothing else. The driver writes it before the resend is sent; `summarize_m4` recomputes it
and refuses a record that carries another value.

**Known before the run.**

| fact | consequence |
|---|---|
| The server's properties do not report `--sleep-idle-seconds`. | The flag is passed on the command line by the run script and read back only through `is_sleeping` after each gap, which the records carry. A server reporting sleeping under `H-M4LD`, or awake after 100 seconds under `H-M4LS`, has failed a control. |
| `H-M4LD` predicts no death at any gap. | The null is read against a known death: 0013 shows this instrument reading one from twelve requests. "No death from 600 idle seconds" is a bound on this server's defaults at 600 seconds, not a property of caches and not a statement beyond 600. |
| Unrecorded requests of this kind were sent to the `qwen` server on 2026-10-06, before this entry: at the defaults, gaps of 0 and 30; with the timer at 60, gaps of 20 and 80 with a `/props` read 10 seconds in, a gap of 75 with a `/props` read 30 seconds in, and a gap of 100 with a render 70 seconds in. | Nothing from them is evidence and no figure from them appears here. The rule and the schedule are those committed before registration. |
| Not measured: a server restart, and a slot saved to disk and restored across one (process events, to be designed with model switch); requests in flight together; the one-slot configuration (its slot is never cleared with nothing between either, so the same rule would be read); gaps beyond 600 seconds. | Stated in the results entry as what the runs do not show. |

**Status.** `H-M4LD` and `H-M4LS` are `[STRETCH]`: registered, not run. `qwen` runs first.

### 0020 — 2026-10-07 — H-M4LD and H-M4LS held: nothing expires by time; the idle timer ends everything

prior-entries-sha256: f96772b5146477ba9cfa57379f9e0c4f52acff8aa916abdbd56b783dc3e999d9

verdict: H-M4LD = HELD

verdict: H-M4LS = HELD

**Outcome** `[BASELINE]`. The runs registered by 0019 were made at commit `53d4d68`, one after the
other on the same local day, under `caffeinate`. Their records and requests are committed at
`6131b90`. Every figure below is from `summarize_m4 --run` on those files, or from the `server`
field of the records.

| | `qwen`, defaults | `llama`, defaults | `qwen`, timer 60 s | `llama`, timer 60 s |
|---|---|---|---|---|
| run | `20261006T233203Z-qwen-H-M4LD` | `20261006T235604Z-llama-H-M4LD` | `20261007T002022Z-qwen-H-M4LS` | `20261007T002804Z-llama-H-M4LS` |
| outcome | ALL MATCH | ALL MATCH | ALL MATCH | ALL MATCH |
| trials counted, matching | 10, 10 | 10, 10 | 6, 6 | 6, 6 |
| resend reused *n* − 1 | at every gap, 10 of 10 | 10 of 10 | at 20 s, 3 of 3 | 3 of 3 |
| resend reused 0 | none | none | at 100 s, 3 of 3 | 3 of 3 |
| resend reused anything else | 0 | 0 | 0 | 0 |
| `is_sleeping` after the gap | false, 10 of 10 | false, 10 of 10 | false at 20 s, true at 100 s | the same |
| recorded gap, seconds | 0.0, 2.0, 4.0, 60.0, 600.0 | the same | 20.0, 100.0 | the same |
| anchors reusing 0 | 10 of 10 | 10 of 10 | 6 of 6 | 6 of 6 |
| slots, context, as the server reported | 4, 40,960 | 4, 50,944 | 4, 40,960 | 4, 50,944 |
| *n*, over all requests | 4,864 to 4,872 | 5,643 to 5,650 | 4,866 to 4,873 | 5,644 to 5,649 |
| local date | one, all records | one | one | one |
| fields not reported | None. | None. | None. | None. |

**Verdict.** Every counted trial of both models matches, in both configurations. By the rule of 0019,
`H-M4LD` is `HELD` and `H-M4LS` is `HELD`.

**What the runs bound and do not locate.** At the defaults the prefix was whole after 600 idle
seconds on both models, with the server reporting awake throughout: a bound at ten minutes, well
beyond the longest idle the recorded agent runs show (3.9 s, 0019), and not a statement about longer
gaps. With the timer at 60 seconds the prefix was whole at 20 and gone at 100 on both models, with the
server reporting sleeping before each resend at 100: the death is located between 20 and 100 seconds,
read at 60 to 61 from the source (0019), not measured finer. Nothing here measures how long the
reload took; the recorded gap excludes it by construction.

**What it does not show.** A server restart, and a slot saved and restored across one (to be
registered with model switch). Requests in flight together. The one-slot configuration. Gaps above
600 seconds. Whether the idle timer's death is partial under any setting: the source frees every slot
and the whole cache, and the runs read 0.

**Status.** `H-M4LD` and `H-M4LS` are `[BASELINE]`, no refuter yet. Four kinds of event are now
measured on this engine: the position of a byte change (0007, 0009, 0016, 0017), eviction by other
requests (0013), idle time (this entry: none), and the engine's one timer (this entry). Three causes
remain `[FUTURE]`: rebuild, model switch, lifespan on recorded runs.

### 0021 — 2026-10-07 — 0020 survived a refuter: H-M4LD and H-M4LS are [VALIDATED]

prior-entries-sha256: 651809f5ced1dd1947e0aba7c6833341f85700f5bc4771e13bac7e132329b250

**Under rule 5** (entry 0008). The results of 0020 were given to a fifth refuter, independent of the
author as in 0010, 0011, 0014 and 0018: a separate session with no access to the one that produced
the code and the entries, nor to the earlier refuters' work.

| | |
|---|---|
| what it read | An export of commit `d89a89b`, the whole tree; llama.cpp's `server-queue.cpp` and `server-context.cpp` at the pinned commit, fetched by itself. It opened the ledger, the configs, the manifest, the four record files and all 32 stored requests, checking each against its own hash; it parsed `config/m4.toml` itself and imported nothing from the package. Denied git, it could not check the commit hashes the entries name; it verified internal consistency of the records, not that the runs happened as described. |
| the brief | Recompute every cell of 0020's table from the records and stored requests alone, and each prediction from the registered config; try to break the controls: nonces, hashes, gaps recomputed from raw timestamps against the margin, record order and density, one date per trial, the counts and the two reuse fields, the prediction stored before the resend; re-read the timer machinery at the pin; look for other explanations for the zeros at 100 seconds and the survivals at 600. |
| verdict | Figures: NOT REFUTED. Meaning: NOT REFUTED. "Every cell of 0020's table reproduces from the raw records and stored requests; zero mismatches. The pinned source supports the reading at every cited line, and the entry's bounds language does not outrun the records." |

**What it tried and what survived**, from its report.

| tried | found |
|---|---|
| Every figure of 0020, with its own code. | All four runs reproduce: 10, 10, 6 and 6 of their trials matching; every anchor reused 0; every recomputed gap inside its registered window; the `is_sleeping` pattern exactly as 0020 states; the *n* ranges, slots and contexts as tabled; no field missing in any of the 64 records. |
| The record files as evidence. | Sequence numbers dense from 1 with timestamps monotonic and no interleaving; 32 distinct requests under 32 distinct nonces, each nonce present in its body; each request file's name equals the hash of its body; token counts, reuse fields and sums agree in all 64 records; the stored predictions equal its own recomputation from the config; every prompt fits the per-slot context. |
| The strongest counter-cases it could name: a prediction copied into the observation, or a trimmed run. | Both fail: predictions were recomputed independently, and the record counts equal the registered schedule exactly, dense and monotonic. |
| The source behind the reading. | Only metrics tasks leave the idle timer untouched (`server-queue.cpp` 24–26); a negative setting never sleeps (292–294); the check runs on a one-second wait (289); the timer shifts past slot work (313–316) and resets on wake (349). Entering sleep frees the contexts (`server-context.cpp` 949–963, 965–981); the reload builds a new prompt cache (1371); the properties endpoint bypasses the sleep wait, posts no task and reports the sleeping state (4816–4824); the render and tokenize endpoints go through the wake path (4241–4249, 5071, 5096), which the driver avoids by preparing the anchor first. |
| Whether anything but the timer could zero the 100-second resends. | Outside traffic cannot be excluded by records alone, but the sleeping state read false at 20 and true at 100 across three trials on each model, with every 20-second resend reusing *n* − 1 in the same runs, leaves no plausible alternative. |
| Whether the 600-second survivals could come from the cache rather than the held slot. | The records cannot distinguish the two; 0020's prose is mechanism-neutral ("the prefix was whole"), so no overclaim; 0019's slot reading is a source reading and labeled as such. |

**Three precisions it added**, kept on record. The exported tree's config files carried the
checkout's line endings, and the records' config hashes match after normalizing them; the repository
hashes configs as text, so a reader hashing raw checkout bytes on Windows will false-alarm. A stored
request's file name hashes the body field it contains, the bytes sent on the wire, not the file's own
bytes. And the render and tokenize endpoints do not merely wait out a sleeping server: the wait path
actively wakes it, which strengthens, not weakens, the rule that the driver sends nothing inside a
gap.

**Consequences.** `H-M4LD` and `H-M4LS` are `[VALIDATED]`.

**Status.** Eight hypotheses on this engine, all `[VALIDATED]`: `H-M1L1`, `H-M1LD`, `H-M7LD`,
`H-M2L1`, `H-M3L1`, `H-M3LD`, `H-M4LD`, `H-M4LS`. Five kinds of event are measured and refuted
without result; three causes remain `[FUTURE]`: rebuild, model switch, lifespan on recorded runs.

### 0022 — 2026-10-09 — Controls registered on vLLM at a pinned commit, one model, two block sizes

prior-entries-sha256: 8e9389c9128521a217d0e3d5fa61197be3bd5ff269c2684727fe6338d26cbbde

**Registers** `config/vllm.toml`, now `registered_by = "0022"`. `config/controls.toml` is registered
since entry 0002 and its request parameters carry over unchanged. No hypothesis is registered and no
verdict cell is added: a control's outcome per block size is PASS, FAIL or NOT MEASURABLE, and a
later entry states it from `summarize_vcontrols` output.

**Instrument.**

| part | value |
|---|---|
| engine | vLLM, commit `b6d8e8afd985f5711eee68e343d2ce908d166488`, built from source on the machine (no release artifact exists for this platform). `GET /version` must report `0.31.1rc1.dev8+gb6d8e8afd`, which carries the commit. |
| backend | The CPU backend on Apple silicon (experimental upstream). dtype bfloat16; `VLLM_CPU_KVCACHE_SPACE=4`; `--max-model-len 16384`; `--enforce-eager`; `--enable-prompt-tokens-details`. |
| model, family `qwen17` | `Qwen/Qwen3-1.7B`, bf16 safetensors, four files each pinned by sha256 in `config/vllm.toml`; the driver hashes every local file and refuses a mismatch. |
| block sizes | 32 and 128, one run per size, the server started fresh per run with `--block-size` passed literally. 128 is this backend's default. 32 is the smallest this backend accepts: its attention kernel refuses any size that is not a multiple of 32 at the pin (`vllm/v1/worker/utils.py`, `select_common_block_size`), which rules out the GPU default of 16. |
| machine | Apple M6, 16 GB of memory, macOS 27.0.1. |

The server does not report its block size; the run script passes it, and the records read it back
only through the block arithmetic below. Every chat body carries `tool_choice: "none"`: the server
refuses a body with tools under its default tool choice unless started with a tool-call parser, and
"none" leaves the rendered prompt unchanged.

**Parameters**, as in `config/controls.toml`: 5 repetitions per block size, each a write, a read and
a scramble; one generated token; temperature 0; a fresh 16-byte nonce per repetition ahead of the
system text, and another for the scramble; scramble words drawn with seed 0; length tolerance 16
tokens.

**Rules.** *n* is the token count of the prompt as the server tokenizes it (`POST /tokenize` of the
same body shape); *B* the run's block size. The cache stores full blocks of *B* tokens; a hit is the
longest stored block chain prefixing the prompt, block-aligned and capped at *n* − 1
(`vllm/v1/core/kv_cache_manager.py` at the pin); `created_cache_tokens` is finalized at the first
output emission, before any generated token is cached, so it counts the prompt's full blocks that
were not a hit (`PrefillStats.finalize` over `estimate_cached_tokens`).

| request | passes when |
|---|---|
| write | cached = 0 and created = floor(*n*/*B*)·*B*. |
| read, the same bytes again | cached = floor((*n* − 1)/*B*)·*B* and created = floor(*n*/*B*)·*B* − cached. |
| scramble | cached = 0 and created = floor(*n*′/*B*)·*B*, with *n*′ within the tolerance of the write's *n*. |
| each of the three | The reported prompt size equals the stored request's token count. |
| a field the server does not report | The run is NOT MEASURABLE. |

The zeros are exact, not bounds: a block matches only whole, and the tokens shared across nonces
(the template head) are fewer than *B*, checked per repetition as lcp(write, scramble) < *B* from
the stored token ids. These rules state rule 1 of entry 0001 for this engine. "Reads what the first
request wrote" is floor((*n* − 1)/*B*)·*B* and not *n*: the hit is block-aligned and the server
recomputes at least the prompt's last token.

**Known before the run.**

| fact | consequence |
|---|---|
| Unrecorded probes of 2026-10-09 exercised both block sizes and both sides of a 128-block boundary. | Nothing from them is evidence and no figure from them appears here. They refuted an earlier reading of created — that it includes the block the generated tokens complete — and the backend's refusal of block 16 was found there. The rules above are those of `src/prefix_mortality/summarize_vcontrols.py` as committed with this entry, after that correction. |
| Prefix caching is on by default on this backend and the server is started fresh per run. | The cache opens empty; the write of repetition 1 meets nothing. |
| `/tokenize` token pieces are BPE-internal and do not join to the rendered text. | The rendered prompt is read back through `/detokenize`; the stored ids, not the pieces, carry every check. |

**Status.** The V controls are `[STRETCH]`: registered, not run.

### 0023 — 2026-10-10 — V controls pass at both block sizes

prior-entries-sha256: c2a508556a40f5acfdfdabf586c9e469a4fabb781db0b3a773904298a23f203d

**Outcome** `[BASELINE]`. The V controls registered by 0022 ran at commit `23c1eb8`, one run per
registered block size, the server started fresh for each. Their records and requests are committed
at `8e20ee0`. Every figure below is from `summarize_vcontrols --run` on those files, or from the
`server` field of the records.

| | block 32 | block 128 |
|---|---|---|
| run | `20261010T150245Z-qwen17-b32` | `20261010T151204Z-qwen17-b128` |
| outcome | PASS | PASS |
| requests | 15 | 15 |
| read: cached = floor((*n* − 1)/*B*)·*B*, created completes floor(*n*/*B*)·*B* | 5 of 5 | 5 of 5 |
| write: cached 0, created = floor(*n*/*B*)·*B* | 5 of 5 | 5 of 5 |
| scramble: cached 0, length within tolerance | 5 of 5 | 5 of 5 |
| *n* | 4,864 to 4,872 | 4,867 to 4,871 |
| largest gap, scramble *n* against write *n* | 4 | 4 |
| nonce isolation, lcp(write, scramble) < *B* | 5 of 5 | 5 of 5 |
| engine version, as the server reported | `0.31.1rc1.dev8+gb6d8e8afd` | `0.31.1rc1.dev8+gb6d8e8afd` |
| fields not reported | None. | None. |

**What the outcome does not show.** At these prompt lengths the records do not witness the block
size: every *n* fell in a span where *n* mod 128 is below 32, so floor(*n*/32)·32 and
floor(*n*/128)·128 are the same number for every request, and a server at either block size would
have produced identical counters. The block size in each record is what the run script passed on the
server's command line; the server does not report it. The unrecorded probes of 2026-10-09 did land
prompts on both sides of a 128-block boundary and read the arithmetic there, but nothing from them
is evidence. A registered boundary repetition would close this; none is registered by this entry.

**Status.** The V controls are `[BASELINE]`: rule 1 of entry 0001 is stated and measured for this
engine at both registered block sizes. `[VALIDATED]` waits on an independent refuter (rule 5,
entry 0008).

### 0024 — 2026-10-10 — 0023 survived a refuter: the V controls are [VALIDATED]

prior-entries-sha256: 369ab60e8915da975bd28eff18b4d05e77dfc52c588ea24b7072c0056d0107a8

**Under rule 5** (entry 0008). The results of 0023 were given to a sixth refuter, independent of the
author as in 0010, 0011, 0014, 0018 and 0021: a separate session with no access to the one that
produced the code and the entries, nor to the earlier refuters' work.

| | |
|---|---|
| what it read | An export of commit `c09b892`, the whole tree. It opened the ledger, the configs, the two record files and all 20 stored requests, recomputed every hash itself, and imported nothing from the package. Denied git, it could not check the commit hashes the entries name; it verified internal consistency of the records, not that the runs happened as described, and it could not re-contact the server, so the usage counters, the version string and the stored tokenizations are trusted as recorded. |
| the brief | Recompute every cell of 0023's table from the records and stored requests alone under 0022's rules; recompute 0023's chain line and every record's config hashes; confirm or refute the entry's own disclosure that these prompt lengths cannot discriminate the block size; look for undisclosed weaknesses: nonce reuse, non-monotonic order, bodies departing from the registered parameters, record fields contradicting the registration. |
| verdict | All six claims: NOT REFUTED. "Zero rule failures" across the 30 records; "no undisclosed weakness found". |

**What it tried and what survived**, from its report.

| tried | found |
|---|---|
| Every figure of 0023, with its own code. | All 30 records satisfy the registered rules: every read cached = floor((*n* − 1)/*B*)·*B* with created completing floor(*n*/*B*)·*B*; every write and scramble cached 0 with created = floor(*n*/*B*)·*B*; every reported prompt size equals its stored token count; 15 records and 5-of-5 rows per run; *n* spans and the largest scramble gap (4, both runs) as tabled; no observed field null anywhere. |
| The record files as evidence. | `seq` dense from 1 with `ts_start` monotonic in both runs; exactly 10 distinct nonces per run with no cross-repetition reuse; read and write share one request file per repetition, 10 of 10, and each file's name equals the hash of the body it contains; all 30 bodies carry the registered parameters (one generated token, temperature 0, `tool_choice: "none"`); every record carries the registered model name, dtype, cache space and engine pin. |
| The chain and the config hashes. | 0023's prior-entries-sha256 reproduces from the normalized entries section exactly; both config hashes reproduce under the repository's text-hash convention in all 30 records — and only under it, since the export carries checkout line endings. |
| The entry's own disclosure. | Confirmed by recomputation: *n* mod 128 stays below 32 in all 30 requests (largest 8), so the 32- and 128-block arithmetic coincide on every one, and the counters cannot discriminate the block size. Its strongest counter-case is this same point: the block size in the records is what the run script passed, not a server report. 0023 states that accurately and stays `[BASELINE]` on it. |
| The one boundary that occurred. | The block-32 run's first scramble landed on *n* = 4,864, a multiple of both block sizes, where a full hit would be indistinguishable from the created figure; cached 0 there is what the lcp guard predicts, and the recomputed lcp is 4. |

**Consequences.** The V controls are `[VALIDATED]`: rule 1 of entry 0001 is stated, measured and
refuter-checked for this engine at both registered block sizes. The block size itself remains
operator-asserted at these prompt lengths, as 0023 discloses; a registered boundary repetition would
make it record-witnessed.

**Status.** Two engines carry validated instruments. On llama.cpp, eight hypotheses, all
`[VALIDATED]`; on vLLM, the controls are `[VALIDATED]` and no hypothesis is registered yet. Three
causes remain `[FUTURE]`: rebuild, model switch, lifespan on recorded runs.

### 0025 — 2026-10-10 — Edit position registered on vLLM: H-M1V32 and H-M1V128

prior-entries-sha256: ec75fa854d78bd26609a27c9d1ef020b76f0ea1773eba99c216ebaff8de449e9

**Registers** `config/vm1.toml`, now `registered_by = "0025"`, and two hypotheses, each with its own
verdict cell. Engine, model, machine and block sizes are those of 0022; the request parameters are
those of `config/controls.toml`.

**Ids.** Rule 2 of 0001 gives `H-M<n><instrument>`. The configuration's block size is appended, the
two configurations being separate hypotheses as ruled for M1 on 2026-09-29 and for this experiment on
2026-10-10. One model is a single cell in each.

| id | server | predicted counters of the edited request |
|---|---|---|
| `H-M1V32` | 0022's flags with `--block-size 32`, started fresh for the run. | cached = floor(min(*d*, *n* − 1)/32)·32; created = floor(*n*/32)·32 − cached. |
| `H-M1V128` | The same with `--block-size 128`. | cached = floor(min(*d*, *n* − 1)/128)·128; created = floor(*n*/128)·128 − cached. |

*d* is the number of leading tokens the base prompt and the edited prompt have in common, under the
server's own tokenizer, each prompt as the server renders it; *n* is the token count of the edited
prompt. The formulas are 0022's rules (validated by 0024) applied to a partial match: a hit is a
stored block chain prefixing the prompt, block-aligned, capped at *n* − 1, and nothing past the first
differing token can match because a block hashes its parent chain.

**A trial** is two requests under one fresh nonce: the base request, then the same request with one
word replaced by `zebra`, a word that occurs nowhere in the base prefix. The 13 sites are
byte-identical to `config/m1.toml`'s (ruled 2026-10-10, so every site compares across engines): the
word at 0, 0.1, 0.24, 0.27, 0.32, 0.5, 0.75 and 0.999 of the system text's length; the first word of
the description of tools 0, 4, 9 and 13; and the first word of the user message. Each site is tried
5 times: 65 trials and 130 requests per hypothesis. A fraction names a place in the system TEXT; its
place in the PROMPT is smaller, since the tools render after the system text and dominate the token
count.

**What decides.**

| case | rule |
|---|---|
| A trial matches. | The edited request's cached and created both equal their predictions, and each request's reported prompt size equals its stored token count. |
| `HELD` | Every trial of both runs matches. |
| `NOT CONFIRMED` | At least one trial does not match. The results entry states the prediction and the observation of every trial. |
| A control fails. | The base request reads cached other than 0 or created other than floor(*n*/*B*)·*B*, or shares a full block with the previous trial's base (checked as lcp from the stored ids). The run stops, and no verdict follows from it. |
| NOT MEASURABLE | The server does not report a field. The verdict stays `unresolved`. |

A prediction is a function of the two stored prompts and the hypothesis's block size, and of nothing
else; it is stored before the edited request is sent, and `summarize_vm1` recomputes it from the
stored tokens and refuses a record that carries another value.

**Known before the run.**

| fact | consequence |
|---|---|
| The server does not report its block size, and at prompt lengths where *n* mod 128 < 32 the counters of the CONTROLS cannot discriminate it (0023). | Here the sites spread *d* across the prompt, so most trials discriminate: a trial whose min(*d*, *n* − 1) mod 128 is 32 or more predicts different cached values under the two hypotheses, and a server at the wrong block size fails its run's predictions. |
| Three unrecorded trials of this kind were sent to a block-32 server before this entry. | Nothing from them is evidence and no figure from them appears here. The rules and the sites are those committed at `8c0e671`, before that contact. |

**Status.** `H-M1V32` and `H-M1V128` are `[STRETCH]`: registered, not run. `H-M1V32` runs first.
### 0026 — 2026-10-10 — H-M1V32 and H-M1V128 held: the edit position prices the tail, block-aligned

prior-entries-sha256: 25cf3f702e17fe4f4fa4df04a7862b8229a6bf51ddc9822e4a9c3f4cedb38878

verdict: H-M1V32 = HELD

verdict: H-M1V128 = HELD

**Outcome** `[BASELINE]`. The runs registered by 0025 were made at commit `b14dc8f`, one per
hypothesis, the server started fresh for each. Their records and requests are committed at
`0e06e7c`. Every figure below is from `summarize_vm1 --run` on those files, or from the `server`
field of the records.

| | block 32 | block 128 |
|---|---|---|
| run | `20261010T200226Z-qwen17-H-M1V32` | `20261010T213957Z-qwen17-H-M1V128` |
| outcome | ALL MATCH | ALL MATCH |
| trials counted, matching | 65, 65 | 65, 65 |
| failed controls, unmeasurable fields | none, none | none, none |
| *d*, over all trials | 34 to 4,865 | 33 to 4,863 |
| *n*, over all requests | 4,864 to 4,874 | 4,865 to 4,874 |
| trials whose two predictions differ | 57 of 65 | 57 of 65 |
| engine version, as the server reported | `0.31.1rc1.dev8+gb6d8e8afd` | `0.31.1rc1.dev8+gb6d8e8afd` |
| local date | one, all records | one |
| fields not reported | None. | None. |

**Verdict.** Every trial of both runs matches: the edited request's cached and created equal
floor(min(*d*, *n* − 1)/*B*)·*B* and floor(*n*/*B*)·*B* minus it, under each server's own *B*. By
the rule of 0025, `H-M1V32` is `HELD` and `H-M1V128` is `HELD`.

**The same edit, priced by each configuration.** Observed cached of the edited request by site;
a set shows the values where *d*'s jitter across nonces crossed a block boundary between
repetitions.

| site | cached, block 32 | cached, block 128 |
|---|---|---|
| system-0.000 | 32 | 0 |
| system-0.100 | 192 | 128 |
| system-0.240 | 448 | 384 |
| system-0.270 | {480, 512} | {384, 512} |
| system-0.320 | {576, 608} | 512 |
| system-0.500 | 928 | 896 |
| system-0.750 | 1,344 | 1,280 |
| system-0.999 | 1,728 | 1,664 |
| tool-00 | 1,792 | 1,792 |
| tool-04 | {2,976, 3,008} | 2,944 |
| tool-09 | {3,616, 3,648} | 3,584 |
| tool-13 | 4,704 | 4,608 |
| user | {4,832, 4,864} | 4,736 |

**The block size is now record-witnessed.** 0023 disclosed that at the controls' prompt lengths the
counters could not discriminate the block size. Here they do: in 57 of 65 trials of each run,
min(*d*, *n* − 1) mod 128 is 32 or more, so the two hypotheses predict different cached values —
and each run matched its own hypothesis's prediction on every trial, which a server at the other
registered block size could not have done. The flag's effect is in the records, not only on the
command line.

**What it does not show.** The cap at *n* − 1 was never exercised: every *d* fell at least 8 tokens
short of *n*, as a word replacement must, so a full-prompt re-read is measured by the controls
(0022), not here. One engine pin, one model, one machine, the CPU backend. Nothing here measures
eviction, idle time or a restart on this engine; those are `[FUTURE]`. The cross-engine comparison
the shared sites were built for waits on the same prompt run on llama.cpp with this model family.

**Status.** `H-M1V32` and `H-M1V128` are `[BASELINE]`, no refuter yet (rule 5, entry 0008). On
vLLM the controls are `[VALIDATED]` and the edit-position pair is `[BASELINE]`; on llama.cpp eight
hypotheses stay `[VALIDATED]`.
### 0027 — 2026-10-10 — 0026 survived a refuter: H-M1V32 and H-M1V128 are [VALIDATED]

prior-entries-sha256: 83a764319edf79274a807626874eb9318367532126feb32d676a21eb5ac0db85

**Under rule 5** (entry 0008). The results of 0026 were given to a seventh refuter, independent of
the author as in 0010, 0011, 0014, 0018, 0021 and 0024: a separate session with no access to the one
that produced the code and the entries, nor to the earlier refuters' work.

| | |
|---|---|
| what it read | An export of commit `fc13299`, the whole tree. It read all 260 records and all 260 distinct stored requests, recomputed every figure with its own code, and imported nothing from the package. Denied git, it could not check the commit hashes the entries name; it verified internal consistency of the records, not that the runs happened as described, and it could not re-contact the server, so the usage counters, the version string and the stored tokenizations are trusted as recorded. |
| the brief | Recompute every cell of 0026's two tables from the records and stored requests alone under 0025's rules, not trusting the stored predictions; recompute 0026's chain line and every record's config hashes; confirm or refute the record-witnessing claim and the cap disclosure; look for undisclosed weaknesses: nonce reuse, non-dense order, bodies departing from the registered parameters, stored predictions departing from the recomputation. |
| verdict | All seven claims: NOT REFUTED. "Zero discrepancies found"; "no undisclosed weaknesses". |

**What it tried and what survived**, from its report.

| tried | found |
|---|---|
| Every figure of 0026, with its own code. | Both runs 65 of 65 trials match with predictions recomputed from the stored token ids, never read from the records; every base control passes; isolation lcp(base, previous base) < *B* everywhere; every reported prompt size equals its stored token count; the *d* and *n* spans, the engine version in all 260 records, one local date, and no null field — all as tabled. |
| The per-site cached table. | All 26 cells reproduce exactly, including every set where *d*'s jitter crossed a block boundary. |
| The record-witnessing claim. | min(*d*, *n* − 1) mod 128 is 32 or more in exactly 57 of 65 trials per run, and in every one of them the observed cached differs from the other registered block size's prediction. Its strongest counter-case sought — a trial whose observed cached would also satisfy the other block size, voiding the claim — does not exist. |
| The cap disclosure. | *n* − *d* is at least 8 in all 130 trials; min(*d*, *n* − 1) = *d* always. |
| The chain and the config hashes. | 0026's prior-entries-sha256 reproduces from the normalized entries section exactly, as does every earlier entry's; all three config hashes reproduce in all 260 records under the repository's text-hash convention — and only under it, since the export carries checkout line endings. One cosmetic finding: 0026's heading lacks the leading blank line the other entries carry; the hash covers it either way. |
| The record files as evidence. | `seq` dense from 1 to 130 with timestamps strictly monotonic in both runs; 130 distinct nonces, one per trial, zero reuse; all 260 bodies carry the registered parameters (one generated token, temperature 0, `tool_choice: "none"`); `zebra` present in every edited body and absent from every base body; the sites exactly `config/vm1.toml`'s 13 × 5; every request file's name equals the hash of the body it contains. |

**Consequences.** `H-M1V32` and `H-M1V128` are `[VALIDATED]`: the edit-position rule is stated,
measured and refuter-checked on this engine at both registered block sizes, and the block size
itself is record-witnessed (0026), no longer only operator-asserted as 0023 disclosed.

**Status.** Ten hypotheses, all `[VALIDATED]`: eight on llama.cpp, two on vLLM, over validated
controls on each engine. The cross-engine comparison waits on the same prompt run on llama.cpp with
this model family. Three causes remain `[FUTURE]` on vLLM: rebuild, model switch, lifespan on
recorded runs.
### 0028 — 2026-10-11 — A third family on llama.cpp: Qwen3-1.7B as GGUF, controls registered

prior-entries-sha256: 0791f1fa98db1533d0af74b73c8f24eecc5b52fe5fd90771c57aad7467bd50e1

**Registers** `config/l17.toml`, now `registered_by = "0028"`: the family `qwen17` — the model the V
entries (0022–0027) measured — served by the llama.cpp build registered in 0002, for the
cross-engine comparison the shared sites were built for (0025). No hypothesis is registered and no
verdict cell is added: a control's outcome per server configuration is PASS, FAIL or NOT MEASURABLE,
and a later entry states it from `summarize` output. `config/m1q17.toml` exists in the tree and
stays UNREGISTERED; this entry does not register it.

**Instrument.**

| part | value |
|---|---|
| engine | llama.cpp `b11235` at commit `6c7a87f`, unchanged since 0002. `config/engines.toml` is byte-identical to its registered text — every committed llama.cpp record hashes it, which is why the new family lives in its own file. |
| model, family `qwen17` | `Qwen/Qwen3-1.7B-GGUF`, file `Qwen3-1.7B-Q8_0.gguf`, the only weight file the owner publishes (checked 2026-10-11); sha256 `061b54da…cb1a` pinned in `config/l17.toml` from the Hub's LFS record and verified against the downloaded file. The driver hashes the local file and refuses a mismatch. |
| quantization | Q8_0, where the V lane served bf16 safetensors. The weights differ; nothing measured here depends on them — reuse counters and token counts are functions of the tokenizer, the template and the cache policy, and the tokenizer files ship inside the GGUF from the same owner. The results entry repeats this sentence. |
| server configurations | Two runs: `--parallel 1`, and the defaults — the two configurations every later qwen17 hypothesis names (0006's pattern). Fresh server per run. |
| machine | The Mac mini of 0002. |

**Parameters**, as in `config/controls.toml`, registered since 0002 and unchanged: 5 repetitions per
configuration, each a write, a read and a scramble under the rules of 0002 — the read reuses exactly
*n* − 1; the write and the scramble reuse at most *h*, the tokens that start before the end of the
nonce. Records of this family additionally carry `config/l17.toml` in `config_sha256`; the
summarizer refuses records of this family that do not.

**Known before the run.**

| fact | consequence |
|---|---|
| One unrecorded probe (one write, one read) was sent to a one-slot server under this model before this entry. | Nothing from it is evidence and no figure from it appears here. The rules are 0002's, committed long before that contact; the model pin was committed at `db10dda`, also before it. |
| At the defaults the server runs 4 slots with idle-slot clearing (0005). | The write rule is exercised beyond its floor only from the fifth fresh prompt, as 0002 recorded for the first two families. |

**Status.** The qwen17 controls are `[STRETCH]`: registered, not run. The one-slot run goes first.
### 0029 — 2026-10-11 — The qwen17 controls pass in both configurations

prior-entries-sha256: 9f799a2bbe916619e52e643fc0abd558b636634b6ff4257db1b91429f1aa9559

**Outcome** `[BASELINE]`. The controls registered by 0028 ran at commit `cd446f9`, one run per server
configuration, the server started fresh for each. Their records and requests are committed at
`f43e1d3`. Every figure below is from `summarize --run` on those files, or from the `server` field
of the records.

| | `--parallel 1` | defaults |
|---|---|---|
| run | `20261011T172712Z-qwen17` | `20261011T172745Z-qwen17` |
| outcome | PASS | PASS |
| records | 15 | 15 |
| read reused *n* − 1 | 5 of 5 | 5 of 5 |
| write reused at most *h* | 5 of 5 (first 0; then 4 to 5 of *h* 30 to 37) | 5 of 5 (every write 0) |
| scramble reused at most *h* | 5 of 5 (4 to 5) | 5 of 5 (every scramble 0) |
| slots, context, as the server reported | 1, 40,960 | 4, 40,960 |
| build, as the server reported | `b11235-6c7a87f7e` | `b11235-6c7a87f7e` |
| *n*, over all requests | 4,867 to 4,873 | 4,865 to 4,872 |
| local date | one, all records | one |
| fields not reported | None. | None. |

**Verdict.** Rule 1 of 0001 is stated and measured for the third family: the read reuses exactly
*n* − 1 and the write and the scramble stay within the header bound, in both configurations. The
patterns match the first two families': with one slot the shared template head is reused (0003);
at the defaults idle-slot clearing leaves every fresh prompt an empty slot (0002, 0005).

**Quantization**, as 0028 promised to repeat: the weights are Q8_0 where the V lane served bf16;
nothing measured here depends on them — reuse counters and token counts are functions of the
tokenizer, the template and the cache policy. The prompt tokenizes to 4,865–4,873 tokens here
against 4,864–4,874 on vLLM (0023, 0026): the same family's tokenizer, within nonce jitter of each
other; whether the edit positions agree token for token is settled by a later descriptive entry,
not asserted here.

**Status.** The qwen17 controls are `[BASELINE]`. `[VALIDATED]` waits on an independent refuter
(rule 5, entry 0008); one refuter covering the whole qwen17 cell is planned after the family's
edit-position runs, so these controls and those runs are refuted together. `config/m1q17.toml`
remains UNREGISTERED.
### 0030 — 2026-10-11 — Edit position registered for the qwen17 family: H-M1L1Q17 and H-M1LDQ17

prior-entries-sha256: 7e0200f798a8e4aec6caf52531713fb455280ec7c7d0b7f9d8dabff442fb0350

**Registers** `config/m1q17.toml`, now `registered_by = "0030"`, and two hypotheses, each with its
own verdict cell. The instrument is M1's, validated for two families by 0007–0011; the family is
0028's; the server configurations, rules, sites, replacement word, repetitions and threshold values
are `config/m1.toml`'s, byte-identical (a test holds the parity) — in a separate file only because
the committed M1 records hash `config/m1.toml`, which therefore never changes. The ids carry the
family because the sealed H-M1L1 and H-M1LD verdicts rest on the first two families' evidence and
stay sealed.

| id | server | predicted reuse of the edited request |
|---|---|---|
| `H-M1L1Q17` | `--parallel 1`, started fresh for the run. | *d*, the leading tokens the base and the edited prompt share. |
| `H-M1LDQ17` | The defaults, started fresh for the run. | *d* when *d*/*n* is above 0.10, else 0; a trial within 0.002 of the threshold is reported and not counted. |

**A trial** is 0007's: the base request under a fresh nonce, then the same request with one word
replaced by `zebra` at one of the 13 sites; the prediction is stored before the edited request is
sent, and `summarize_m1` recomputes it from the stored tokens and refuses a record that carries
another value. 5 repetitions per site: 65 trials and 130 requests per hypothesis.

**What decides** is 0006's table, unchanged: `HELD` when every counted trial of the run matches;
`NOT CONFIRMED` on any counted mismatch; a failed base control stops the run and decides nothing;
a field the server does not report is NOT MEASURABLE, never zero. One model family is a single cell
in each hypothesis.

**Why this closes the cross-engine gap.** 0026 priced the 13 edits under vLLM's two block sizes on
this model family; these runs price the same 13 edits (same request bytes) under llama.cpp's two
configurations. A later descriptive entry tabulates *d* and *n* per site per engine from the stored
requests and states whether the engines put each edit at the same token position; the comparison
entry follows it. Neither is registered here.

**Known before the run.**

| fact | consequence |
|---|---|
| Three unrecorded trials (sites system-0.000, system-0.500, user) were sent to a one-slot server under this family before this entry. | Nothing from them is evidence and no figure from them appears here. The rules and sites are those committed at `db10dda`, before that contact. |
| The threshold sites were chosen on the first two families' tokenizers (0006). | Whether 0.24 and 0.27 still bracket the threshold on this tokenizer is read from the run, trial by trial; a trial inside the margin is excluded by the registered rule, not patched. |

**Status.** `H-M1L1Q17` and `H-M1LDQ17` are `[STRETCH]`: registered, not run. `H-M1L1Q17` runs
first.
### 0031 — 2026-10-11 — H-M1L1Q17 and H-M1LDQ17 held: the third family prices edits like the first two

prior-entries-sha256: 5262a7593dbac0dd62c115287f3ade91c8bce04719e46df9586871cb851ff773

verdict: H-M1L1Q17 = HELD

verdict: H-M1LDQ17 = HELD

**Outcome** `[BASELINE]`. The runs registered by 0030 were made at commit `fda21ae`, one per
hypothesis, the server started fresh for each. Their records and requests are committed at
`eb01343`. Every figure below is from `summarize_m1 --run` on those files, or from the `server`
field of the records.

| | `--parallel 1` | defaults |
|---|---|---|
| run | `20261011T174130Z-qwen17-H-M1L1Q17` | `20261011T174738Z-qwen17-H-M1LDQ17` |
| outcome | ALL MATCH | ALL MATCH |
| trials counted, matching | 65, 65 | 65, 65 |
| not counted, near the threshold | 0 | 0 |
| sites at or below 0.10 of the prompt | three; reuse = *d* at every one | the same three; reuse = 0 at every one |
| threshold bracket, shares | — | highest that read 0: 0.0950; lowest that read *d*: 0.1044 |
| *d*, over all trials | 32 to 4,865 | 33 to 4,864 |
| *n*, over all requests | 4,866 to 4,874 | 4,864 to 4,873 |
| slots, build, as the server reported | 1, `b11235-6c7a87f7e` | 4, `b11235-6c7a87f7e` |
| local date | one, all records | one |
| fields not reported | None. | None. |

**Verdict.** Every counted trial of both runs matches: with one slot the edited request reuses
exactly *d*; at the defaults it reuses *d* above the 0.10 threshold and 0 below, with no trial
inside the registered margin on this tokenizer. By the rule of 0030, `H-M1L1Q17` is `HELD` and
`H-M1LDQ17` is `HELD`.

**The cliff, third family.** The threshold sites chosen on the first two families' tokenizers
(0006) bracket the cliff here too: 0.0950 of the prompt read 0, 0.1044 read *d* — the same cliff
0009 measured for the first two families, now on the model the V lane priced block-aligned (0026).
The engines' pricing of the same edits now exists on record for both engines on one family;
stating the comparison, and whether the two engines put each edit at the same token position, is
left to the two entries 0030 names, not asserted here.

**What it does not show.** One engine pin, one machine, Q8_0 weights (0028's sentence applies).
Nothing here measures eviction, idle time, a restart or concurrent requests on this family.

**Status.** `H-M1L1Q17` and `H-M1LDQ17` are `[BASELINE]`. `[VALIDATED]` waits on the one refuter
covering the whole qwen17 cell (0029's plan) after the descriptive and comparison entries.
### 0032 — 2026-10-11 — Descriptive: the two engines put each edit at the same position, within nonce jitter

prior-entries-sha256: ec0059b848e38d3a57511826676ad4dbf8e1a9069ee6ea92b59670710ef9417d

**Descriptive entry; no hypothesis, no verdict cell, no server contact.** Before 0026's and 0031's
runs are compared, this entry settles whether the comparison is of the same token position or only
of the same bytes. The request bodies are byte-identical across engines by construction (0025,
0030); the renders need not be: llama.cpp renders through its own template engine over the
GGUF-embedded tokenizer, vLLM through the HF tokenizer and chat template.

**Figures.** Every number below is `first_differing_token` (*d*) or *n* from the four summarizer-
verified reports of 0026 and 0031 (`results/m1q17/…H-M1L1Q17`, `…H-M1LDQ17`, `results/vm1/…H-M1V32`,
`…H-M1V128`), 10 trials per site per engine. A range spans a site's 10 trials; each trial has its
own nonce, and the nonce alone moves *d* by a few tokens, so a range's width is the nonce jitter.

| site | *d* on llama.cpp, min to max | *d* on vLLM, min to max | ranges overlap |
|---|---|---|---|
| system-0.000 | 32 to 38 | 33 to 37 | yes |
| system-0.100 | 216 to 219 | 213 to 221 | yes |
| system-0.240 | 458 to 463 | 456 to 463 | yes |
| system-0.270 | 508 to 514 | 507 to 516 | yes |
| system-0.320 | 601 to 609 | 601 to 608 | yes |
| system-0.500 | 934 to 940 | 933 to 940 | yes |
| system-0.750 | 1,343 to 1,348 | 1,344 to 1,349 | yes |
| system-0.999 | 1,744 to 1,750 | 1,743 to 1,751 | yes |
| tool-00 | 1,800 to 1,807 | 1,801 to 1,806 | yes |
| tool-04 | 3,003 to 3,010 | 3,004 to 3,009 | yes |
| tool-09 | 3,647 to 3,652 | 3,646 to 3,651 | yes |
| tool-13 | 4,722 to 4,731 | 4,725 to 4,731 | yes |
| user | 4,858 to 4,865 | 4,861 to 4,865 | yes |

*n* spans 4,864 to 4,874 on llama.cpp and 4,865 to 4,874 on vLLM.

**What this does and does not establish.** At every one of the 13 sites the two engines' *d* ranges
overlap: the edit's position differs across engines by no more than the jitter the nonce causes
within one engine. The comparison entry may therefore treat each site as one position on both
engines, at the nonce-jitter resolution (a few tokens — well under both engines' pricing
granularity at every site above the first block). Token-for-token identity is NOT established and
is not claimed: no nonce was reused across engines, so no single prompt was tokenized by both; a
per-trial *d* equality would need that, and nothing here needs it.

**Status.** Descriptive, `[BASELINE]` facts only; it changes no verdict. The comparison entry
follows.
### 0033 — 2026-10-11 — The comparison: one edit, one model family, four prices

prior-entries-sha256: 88a27c62ac0719cd5dcea47f8c362c0d830f697f02df9b9be4a45ae3bb9f4af2

**Descriptive entry; no hypothesis, no verdict cell, no server contact.** This is the comparison the
shared sites were built for (0025, 0030): the same byte-identical edit, priced by every validated or
held configuration on the qwen17 family. By 0032 the engines put each edit at the same position
within nonce jitter, so a row compares one place in the prompt.

**Figures.** Every number is the edited request's observed reuse (llama.cpp `cache_n`) or observed
cached (vLLM) from the four summarizer-verified reports of 0026 and 0031, 10 trials per cell; a
single number means all 10 agreed, a range spans the nonce jitter.

| site | llama.cpp, one slot | llama.cpp, defaults | vLLM, block 32 | vLLM, block 128 |
|---|---|---|---|---|
| system-0.000 | 32 to 38 | 0 | 32 | 0 |
| system-0.100 | 216 to 219 | 0 | 192 | 128 |
| system-0.240 | 458 to 461 | 0 | 448 | 384 |
| system-0.270 | 510 to 514 | 508 to 514 | 480 to 512 | 384 to 512 |
| system-0.320 | 601 to 609 | 603 to 607 | 576 to 608 | 512 |
| system-0.500 | 938 to 940 | 934 to 939 | 928 | 896 |
| system-0.750 | 1,343 to 1,348 | 1,344 to 1,348 | 1,344 | 1,280 |
| system-0.999 | 1,744 to 1,750 | 1,746 to 1,750 | 1,728 | 1,664 |
| tool-00 | 1,800 to 1,807 | 1,800 to 1,805 | 1,792 | 1,792 |
| tool-04 | 3,003 to 3,010 | 3,004 to 3,006 | 2,976 to 3,008 | 2,944 |
| tool-09 | 3,648 to 3,652 | 3,647 to 3,649 | 3,616 to 3,648 | 3,584 |
| tool-13 | 4,726 to 4,731 | 4,722 to 4,729 | 4,704 | 4,608 |
| user | 4,858 to 4,865 | 4,859 to 4,864 | 4,832 to 4,864 | 4,736 |

**What the rows say.** The bytes locate the death: in every configuration the reuse tracks the
edit's position, from almost nothing at the head to almost everything at the tail. The engine's
policy prices it: within one trial's *d*, vLLM at block *B* pays *d* rounded down to a multiple of
*B* — at most *B* − 1 tokens behind llama.cpp's one-slot price of exactly *d*, visible in every row
(block 128 trails by up to 127; block 32 by up to 31). llama.cpp's defaults are not a rounding but a
cliff: the three sites at or below 0.10 of the prompt price to 0 while vLLM still pays 128 to 448
there — the one place a policy inverts the engines' ordering. Where *d*'s jitter crosses a block
boundary a vLLM cell becomes a range (0026's sets); llama.cpp's one-slot ranges are the jitter
itself.

**Sources and what is not claimed.** Rows from
`results/m1q17/20261011T174130Z…H-M1L1Q17`, `…174738Z…H-M1LDQ17` (0031, commit `eb01343`) and
`results/vm1/20261010T200226Z…H-M1V32`, `…213957Z…H-M1V128` (0026, commit `0e06e7c`). Trials are not
paired across engines (no nonce is reused across them), so cells compare distributions at one site,
not single requests. One machine, the CPU backend on V, Q8_0 weights on L against bf16 on V
(0028's sentence); no latency is measured or compared anywhere in this repository.

**Status.** Descriptive; it changes no verdict. The qwen17 cell (0028–0033) awaits its one refuter.
### 0034 — 2026-10-11 — The qwen17 cell survived a refuter: H-M1L1Q17 and H-M1LDQ17 are [VALIDATED], two sentences corrected

prior-entries-sha256: 3e3d06ad2135e93358a2e18c3bb521b14d4153639ba8dfdfcf787a054800c357

**Under rule 5** (entry 0008). The whole qwen17 cell — 0028 through 0033: controls, edit position,
the descriptive *d* table and the comparison — was given to an eighth refuter, independent of the
author as in 0010, 0011, 0014, 0018, 0021, 0024 and 0027.

| | |
|---|---|
| what it read | An export of commit `12cac63`, the whole tree: 550 records across the six runs the entries name, 540 distinct stored requests, every figure recomputed with its own code, nothing imported from the package. Denied git, it could not check the named commits; it could not re-contact the servers, so the reuse counters and tokenizations are trusted as recorded; the local GGUF bytes are outside the tree, so the model pin was checked record-against-config, not file-against-pin. |
| verdict | All seven claim groups: NOT REFUTED on substance. Two discrepancies in entry PROSE, both contradicted by the entries' own correct tables, both reverified by the author and corrected below. |

**What it tried and what survived.** 0029's every cell including the recomputed header bound *h*;
0031's 65 of 65 counted matches per run with *d*, both rules and the stored predictions recomputed
(and the zero-trials-in-the-margin claim verified); 0032's 26 *d* ranges and all 13 overlaps;
0033's 52 cells, with vLLM's cached equal to floor(min(*d*, *n* − 1)/*B*)·*B* in all 260 vLLM
trials; the six chain lines; the model pin in every record; the m1q17–m1 value parity; 280 distinct
nonces with sharing only where designed, none crossing runs or engines; dense `seq`, monotonic
timestamps, registered bodies throughout.

**Corrections.** Entries are immutable; these two sentences are superseded here, and the tables
they contradict stand unchanged.

| entry, sentence | correction |
|---|---|
| 0031, the row label "*n*, over all requests". | The spans tabled (4,866–4,874 and 4,864–4,873) are over the EDITED requests — the registered *n*. Over all 130 requests per run the spans are 4,865–4,874 and 4,863–4,873; base requests run 1 to 2 tokens shorter. No figure changes. |
| 0033, "vLLM still pays 128 to 448 there" and the inversion being "the one place". | At the three low sites vLLM pays {32, 192, 448} at block 32 and {0, 128, 384} at block 128: at system-0.000 under block 128 BOTH policies pay 0, a tie, not an inversion. The inversion holds at the other five low-site cells. The table was right; the sentence overstated it. |

**Consequences.** `H-M1L1Q17` and `H-M1LDQ17` are `[VALIDATED]`; the qwen17 controls (0029) are
refuter-checked the same way. The comparison table (0033, as corrected) is the cross-engine result
the shared sites were built for: twelve hypotheses now `[VALIDATED]` across two engines, and the
same edit priced four ways on one model family is on record with every number refuter-recomputed.

**Status.** Phase 1's measurement program for the blog's central figure is complete. Remaining
`[FUTURE]` on V: rebuild, model switch, lifespan on recorded runs; M3/M2 port cleanly when taken up.
### 0035 — 2026-10-11 — Templating and serialization drift registered on vLLM: H-M3V32/128, H-M2V32/128

prior-entries-sha256: 9b6f96ae2445349b2a313195f352df2445da1285e2397fab957287fc325447ea

**Registers** `config/vm3.toml` (templating) and `config/vm2.toml` (serialization drift), both now
`registered_by = "0035"`, and four hypotheses with their own verdict cells — one entry for the two
sibling experiments, 0015's pattern on the first engine. Engine, model, machine and block sizes are
0022's; request parameters are `config/controls.toml`'s; the instrument is vm1's (0025, validated by
0027) with an arm variant in place of a word edit.

**A trial** is two requests under one fresh nonce: the base request of 0022, then the arm's variant.

| experiment, arm | the variant | expected render, from the unrecorded probes |
|---|---|---|
| vm3 `thinking-off` | the same body plus `chat_template_kwargs {"enable_thinking": false}` | the base's render plus an empty think block APPENDED after the generation prompt: the base is a strict prefix, *d* = the base's token count. |
| vm3 `thinking-on` | the same with `true` | identical to the base (thinking is the template's default). |
| vm2 `keyorder` | every tool's function object with its key order reversed — the same JSON value, different bytes | identical to the base: both engines normalise function-level key order (llama.cpp's S2 and S5, 0016). |
| vm2 `properties` | `parameters.properties` reversed in every tool that has two or more keys — the same JSON value | differs from the first reordered tool on: both engines PRESERVE property order (llama.cpp's S4, 0016; the probe put the first diff at 0.78 of the prompt when only one late tool was reordered). |

The prediction is 0025's one formula, no special case: cached = floor(min(*d*, *n* − 1)/*B*)·*B*,
created = floor(*n*/*B*)·*B* − cached, *d* from the two stored token lists, *n* the variant's count.
An identical render has *d* = *n* and prices as an identical resend through the cap. The expected-
render column above is what the probes SAW; the registered prediction does not depend on it — if a
render differs from the expectation, the formula still prices it and the records show the render.
5 repetitions per arm: 10 trials and 20 requests per hypothesis, one run per hypothesis, the server
started fresh with the hypothesis's block size. What decides is 0025's table verbatim: `HELD` when
every trial of a hypothesis's run matches; a failed base control stops the run and decides nothing;
NOT MEASURABLE is never zero; the stored prediction must equal the summarizer's recomputation.

**Why it is worth registering.** The render semantics turn out to AGREE across the engines: the
thinking switch appends after the generation prompt on both (0017, with 0018's precision, and the
probe here), function-level key order is normalised on both (0016's S2/S5; the probe), and property
order is preserved on both (0016's S4; the probe). What differs is only the price of the same
render: llama.cpp one-slot reuses exactly *d* (an identical render costs one token, an S4-style diff
costs *n* − *d*), while vLLM rounds the same *d* down to a block multiple — an identical render
costs up to *B* and an S4-style diff up to *B* − 1 more than llama.cpp's exact price. These runs
put that on record with the same corpus and the same rewritings as the first engine's 0016/0017.

**Known before the run.**

| fact | consequence |
|---|---|
| Twelve unrecorded probe trials were sent to block-32 servers before this entry: six design probes, then six through the built driver (every registered arm plus one arm dropped in design), 6 of 6 driver probes matching. | Nothing from them is evidence and no figure from them appears here beyond the expected-render column, which the registered prediction does not use. The arm constructions were fixed before any registered run; the dropped arm (the same tools as re-indented JSON text) never reaches the render and is recorded only in the private design notes. |
| The driver and summarizer reuse vm1's evaluation verbatim. | A weakness found in vm1's rules would be a weakness here; vm1 is `[VALIDATED]` (0027), and its refuter recomputed the shared formula from raw bytes. |

**Status.** `H-M3V32`, `H-M3V128`, `H-M2V32`, `H-M2V128` are `[STRETCH]`: registered, not run.
vm3 runs first, block 32 first.
### 0036 — 2026-10-11 — H-M3V32/128 and H-M2V32/128 held: the formula prices templating and serialization drift

prior-entries-sha256: 485406284472026a486d9e80415bf165aa0cee4aed77910ae598b58180e2340c

verdict: H-M3V32 = HELD

verdict: H-M3V128 = HELD

verdict: H-M2V32 = HELD

verdict: H-M2V128 = HELD

**Outcome** `[BASELINE]`. The four runs registered by 0035 were made at commit `ab25c5d`, one per
hypothesis, the server started fresh with the hypothesis's block size, vm3 first, block 32 first.
Their records and requests are committed with this entry. Every figure below is from
`summarize_vm23 --run` on those files, or from the `server` field of the records.

| | H-M3V32 | H-M3V128 | H-M2V32 | H-M2V128 |
|---|---|---|---|---|
| run | `20261011T200704Z…` | `20261011T201632Z…` | `20261011T202605Z…` | `20261011T203820Z…` |
| outcome | ALL MATCH | ALL MATCH | ALL MATCH | ALL MATCH |
| trials counted, matching | 10, 10 | 10, 10 | 10, 10 | 10, 10 |
| failed controls, unmeasurable fields | none, none | none, none | none, none | none, none |
| *d*, over all trials | 4,864 to 4,871 | 4,865 to 4,870 | 2,128 to 4,870 | 2,127 to 4,870 |
| *n*, over all edited requests | 4,865 to 4,875 | 4,865 to 4,874 | 4,863 to 4,871 | 4,866 to 4,872 |
| engine version, as the server reported | `0.31.1rc1.dev8+gb6d8e8afd` | same | same | same |
| local date | one, all records | one | one | one |
| fields not reported | None. | None. | None. | None. |

**Verdict.** Every trial of all four runs matches: the variant's cached and created equal
floor(min(*d*, *n* − 1)/*B*)·*B* and floor(*n*/*B*)·*B* minus it, under each server's own *B*. By
the rule of 0035, all four hypotheses are `HELD`.

**The arms, priced.** Observed cached/created of the variant by arm; a set shows the values where
the nonce's token-length jitter crossed a block boundary between repetitions. The renders came out
as the probes expected: `thinking-off` appended 4 tokens after the generation prompt (*n* − *d* = 4
in every trial, the base a strict prefix), `thinking-on` and `keyorder` rendered identically
(*d* = *n*), and `properties` diffed at *d* ≈ 2,130 of ≈ 4,870 (share 0.44 — every tool with two or
more properties reordered, so the first diff sits at the first such tool).

| arm | cached/created, block 32 | cached/created, block 128 |
|---|---|---|
| thinking-off | 4,864 / 0 | 4,864 / 0 |
| thinking-on | 4,864 / 0 | 4,864 / 0 |
| keyorder | {4,832, 4,864} / 0 | 4,864 / 0 |
| properties | 2,112 / 2,752 | 2,048 / 2,816 |

What the table says: templating drift that only APPENDS (the thinking switch) and serialization
drift the template normalises away (function-level key order) are priced as an identical resend —
the whole cap, nothing more, at either block size (4,864 happens to be a multiple of both 32 and
128; `keyorder`'s 4,832 is one trial whose *n* = 4,863 put the *n* − 1 cap below it). Property-order
drift the template PRESERVES kills the prefix at the first reordered tool and the block size prices
the corpse: block 128 recomputes 64 more tokens than block 32 for the same *d*, where llama.cpp's
one-slot reuse would pay exactly *n* − *d* (0016's S4). Same renders, same death site, engine
policy prices it.
### 0037 — 2026-10-11 — 0036 survived a refuter: H-M3V32/128 and H-M2V32/128 are [VALIDATED]

prior-entries-sha256: ec58fadc808d1227ad51cb4465d3aee9f06866fb451406ad29012428f1011994

**Under rule 5** (entry 0008). The results of 0036 were given to a ninth refuter, independent of
the author as in 0010, 0011, 0014, 0018, 0021, 0024, 0027 and 0034: a separate session with no
access to the one that produced the code and the entries, nor to the earlier refuters' work.

| | |
|---|---|
| what it read | An export of commit `df7527e`, the whole tree. It read all 80 records of the four runs and their stored requests, recomputed every figure with its own code, and imported nothing from the package. Denied git, it verified internal consistency of the records, not that the runs happened as described, and it could not re-contact the server, so the usage counters, the version string and the stored tokenizations are trusted as recorded. |
| the brief | Recompute every trial of the four runs under 0035's formula from the stored token ids alone; recompute 0036's two tables, its render claims (the appended think block, the identical renders, the properties diff share), its chain line and 0035's, and every record's config hashes; check arms against the registered configs, nonce pairing and distinctness, block sizes, the engine version pin, and every prose claim against the raw records. |
| verdict | NOT REFUTED. "Entry 0036's four HELD verdicts, every figure, and the hash chain all reproduce from raw bytes." |

**What it tried and what survived**, from its report.

| tried | found |
|---|---|
| Every trial, with its own code. | 40 of 40 trials match the formula with *d* recomputed as the stored token lists' common prefix; every base control reads cached 0; 10 base + 10 edited per run, paired by nonce, 40 nonces all distinct. |
| 0036's two tables. | The *d* and *n* ranges of all four runs and every cell of the price table reproduce exactly, including `keyorder`'s single 4,832 trial, whose *n* = 4,863 matches the prose explanation. |
| The render claims. | `thinking-off`: *n* − *d* = 4 in all 20 trials with the base a strict prefix; `thinking-on` and `keyorder`: *d* = *n* = the base's count in all 20; `properties`: shares 0.4371 to 0.4378. |
| The records as evidence. | Sites match the registered arms in both configs; block size matches the hypothesis in all 80 records; the engine version equals `config/vllm.toml`'s pin everywhere; one local date per run; `observed` equals the raw usage everywhere. |
| The chain and the config hashes. | 0035's and 0036's prior-entries-sha256 reproduce from the normalized entries section; the config hashes in the records reproduce under the repository's text-hash convention — and only under it, the export carrying checkout line endings, as the seventh refuter also noted. |

**Consequences.** `H-M3V32`, `H-M3V128`, `H-M2V32` and `H-M2V128` are `[VALIDATED]`: sixteen
validated hypotheses across two engines. The drift half of the program is closed on vLLM — the
same renders die at the same sites on both engines (0016/0017, the probes of 0035), and the price
of the death is engine policy: exact *d* on llama.cpp, block-rounded *d* on vLLM.
### 0038 — 2026-10-11 — Lifespan on recorded runs registered on llama.cpp: H-M8L1, H-M8LD

prior-entries-sha256: 182f7f81542d417bce8c5f91ca45465ffd9625c842ab7d45c581d48dc046d295

**Registers** `config/m8.toml`, now `registered_by = "0038"`, and two hypotheses. Engine, models and
machine are those of 0002, the request parameters (one token generated, temperature 0) those of
`config/controls.toml`. The similarity threshold (0.10), the cache size (8192 MiB) and the KV
geometry restate `config/m7.toml`'s values (0012), because that file is sealed by the hashes in its
records.

**Id.** `M8` is the eighth cause of 0001, lifespan along real conversations; `1` and `D` as in 0006.
Ruled by the operator on 2026-10-06 and 2026-10-11: both 8B families; no per-conversation nonce (a
deployment shares its system prompt across conversations, and a replay is not an isolated trial);
Llama with `tools_in_user_message: false` (the conversations open with an assistant greeting, which
its template otherwise takes as the user message that carries the tools); one registering and one
results entry per experiment.

| id | server | the records must say | predicted reuse of each request |
|---|---|---|---|
| `H-M8L1` | Started with `--parallel 1`. | 1 slot, and a slot context every request fits. | The policy below over the stored token lists, sent one conversation after another in file order, all fifty. |
| `H-M8LD` | Started with no flag but the model. | 4 slots, and a slot context every request fits. | The same policy, the *C* conversations with the most assistant turns sent in round robin, one run per *C* in {2, 6, 12}: tasks 12 and 44; those plus 18, 10, 23, 14; those plus 24, 48, 7, 32, 4, 21. |

**The replay.** `corpus/recorded/tau2-airline-claude-3-7-sonnet/` holds fifty of tau2-bench's
published airline conversations (0019; 762 assistant turns, 3 to 52 per conversation). For each
assistant turn the driver sends the fixture's system text and tool schemas followed by every recorded
message before that turn, in the OpenAI chat shape (`prefix_mortality.replay`), and reads the reuse.
The first turn of every conversation is the greeting, so its request carries the system text and the
tools alone and is byte-identical across conversations. Every request fits both slot contexts (the
largest conversation is about 14,000 tokens; the records carry 40,960 and 50,944).

**The reading** (`tools/server/server-context.cpp` 1558–1668, 2447–2463 and 551; `server-task.cpp`
1710–1775 and 1793–1830 at the pin), implemented once as `prefix_mortality.slotsim` and fed the stored
token lists in send order:

| the server does | so |
|---|---|
| A request goes to the idle slot whose held prompt shares the largest fraction of the request above 0.10 (lcp over the request's length); with none, to the least recently used slot. | A conversation's request finds whichever slot holds a prompt sharing its head. |
| A slot chosen by similarity is saved to and searched in the prompt cache **only if** the request would keep under half of the slot's prompt (`f_keep < 0.5`); an LRU-chosen slot always is. | Two conversations sharing a 4,800-token head and holding under 9,600 tokens take each other's slot without a cache search: each reuses only the shared head and re-prompts its own history, and neither's state is ever restored. Past 9,600 tokens the cache is searched. |
| A cached prompt replaces the slot's only if at least a quarter of it is kept and it beats the slot's prompt on both the kept fraction and the similarity, strictly, entries tried in arrival order. A save is skipped when the prompt is already a prefix of a cached one and erases cached prompts that are prefixes of it; a state larger than the limit is not cached; the oldest entries go until the new one fits. One token's state is the registered geometry. | The cache holds one state per conversation, the newest; a conversation whose state was evicted re-prompts from the shared head. |
| The reuse is the common prefix of the slot's prompt and the request, one below the request's length when the prompt is wholly held (0003). After the request the slot holds the prompt — a slot that stops after its first sampled token is released without it (line 551 runs only for a slot that keeps generating) — and every other idle slot is saved and cleared (`--cache-idle-slots`, `--kv-unified`, both on at the defaults). | A request that extends its conversation's previous request reuses exactly that request's token count. The one generated token is recorded as text and never held. |

A prediction is a function of the stored token lists sent before it, the registered constants and
the policy, and of nothing else. The driver writes it before the request is sent, with the policy's
intermediate readings (slot chosen by similarity or LRU, kept fraction, cache searched, saved,
restored, erased, evicted); `summarize_m8` recomputes all of it from the stored tokens and refuses a
record that carries another value. A request the policy decides by one token or less is reported and
not counted, as 0006's margin.

**A run** is the whole schedule, one request per assistant turn: 762 requests for `H-M8L1`; for
`H-M8LD` the turns of the chosen conversations, each conversation dropping out when it ends. The
server is started fresh for each run. What the run measures, per conversation: the share of its tokens
served from a held prefix, and its deaths — requests that reused less than the common prefix with the
conversation's own previous request. The first request of a conversation has no own previous request;
what it reuses from another conversation's held prompt is the shared head, predicted and counted.

**What decides.**

| case | rule |
|---|---|
| A request matches. | Its reuse equals the prediction, and its two counts add up to its token count and its two reuse fields agree. |
| `HELD` | Every counted request of every run under the hypothesis matches, on both models. |
| `NOT CONFIRMED` | At least one counted request does not match. The results entry states, per run, every mismatching request with its prediction and its reading, and what the policy read at that request. |
| A control fails. | The first request of a run reuses anything but 0; a request's counts do not add up or its reuse fields disagree. The run stops, and no verdict follows from it. |
| NOT MEASURABLE | The server does not report a field or a slot context; a request has at least as many tokens as the slot context; the local date changed inside a run. The verdict stays `unresolved`. |
| The records say another number of slots, more than one slot context, a *C* not registered, a corpus other than the vendored one, or requests out of the registered schedule. | The run is not that experiment. |

**Known before the run.**

| fact | consequence |
|---|---|
| Twenty-seven unrecorded requests were sent before this entry, on 2026-10-11: `qwen` at one slot (5, conversation 12) and at the defaults (8, conversations 12 and 18 interleaved); `llama` at one slot (4 + 4, conversation 12) and at the defaults (6, the same two). | Nothing from them is evidence and no figure from them appears here beyond the head's size above, which the registered prediction does not use. One of them refuted a first reading: the held prompt was taken to include the one sampled token, and a Llama turn whose generated token equalled the recorded continuation's first token read one less than predicted. The source (line 551) settles it as stated above; the reading registered here is the corrected one, and the policy was probed again under it. |
| The prediction is a policy, not a formula. | What a mismatch refutes is the reading of the policy at that request; the summarizer reports which branch the policy took, so a results entry can say where the reading failed. The simulator is checked against the test stand-in on random sequences, and the stand-in is written from the same lines; agreement shows the two readings agree, not that either is right — the runs do that. |
| The cache's token-count pass (`limit_tokens`) is not modelled: it is off at the defaults, and with the size limit set it binds no earlier than the size pass. | A cliff earlier than the size pass predicts would be a result about that reading. |
| The per-request time is dominated by prompt processing after a death: a conversation that re-prompts 5,000 to 14,000 tokens on this machine takes tens of seconds per request. | A run under `H-M8LD` at *C* = 12 is long (about an hour per model) and no run crosses local midnight; the records carry the date. |
| Not measured: requests in flight together; conversations other than the vendored fifty; a server with a cache size other than the default. | Stated in the results entry as what the runs do not show. |

**Status.** `H-M8L1` and `H-M8LD` are `[STRETCH]`: registered, not run. `qwen` runs first, one slot
first.
### 0039 — 2026-10-11 — Rebuild registered on llama.cpp: H-M5L1, H-M5LD, H-M5LC

prior-entries-sha256: d04fb66cb4a0e0ef84a36f112afcc44243b2f7d21442a0e27335505aa80a5035

**Registers** `config/m5.toml`, now `registered_by = "0039"`, and three hypotheses. Engine, models and
machine are those of 0002, the request parameters those of `config/controls.toml`; each trial runs
under its own nonce, as the M1 trials do. The similarity threshold (0.10) and its margin (0.002)
restate `config/m1.toml`'s (0006).

**Id.** `M5` is the fifth cause of 0001, rebuild: the client rewriting its own context, as an agent
harness does when it compacts. `1` and `D` as in 0006; `C` is a server started with `--cache-reuse`
(ruled 2026-10-06 §9). Ruled by the operator on 2026-10-11: both 8B families; one registering and one
results entry per experiment.

| id | server | the records must say | predicted reuse of the compacted request |
|---|---|---|---|
| `H-M5L1` | Started with `--parallel 1`. | 1 slot, a slot context both requests fit. | *d*, the tokens the two stored prompts share from the start (0010's prefix rule). |
| `H-M5LD` | Started with no flag but the model. | 4 slots, the same. | *d* when *d*/*n* is above 0.10, else 0 (0010's threshold rule); a trial within 0.002 of the threshold is reported and not counted. |
| `H-M5LC` | Started with `--parallel 1 --cache-reuse 256`. | 1 slot, the same. | *d* plus every later run of at least 256 tokens the walk below matches, one below *n* when that is the whole request. |

**A trial** is two requests under one fresh nonce: a recorded conversation
(`corpus/recorded/tau2-airline-claude-3-7-sonnet/`, 0019) replayed in full at its last assistant turn
— the fixture's system text behind `run <nonce>`, the tool schemas, every recorded message before that
turn — and the same conversation compacted at its midpoint: the messages from the first user message
up to the last user message before the middle assistant turn are removed (`trim`) or replaced by one
user message carrying the registered summary text (`summary`). The ten conversations with the most
assistant turns (tasks 12, 44, 18, 10, 23, 14, 24, 48, 7, 32), two arms each: 20 trials and 40 requests
per run, six runs. The full request is a control inside the trial: a fresh prompt reuses at most the
tokens before its nonce (0003, 0009).

**The reading** (`tools/server/server-context.cpp` 3225–3300 and 3414–3416 at the pin). With
`--cache-reuse N` (0 at the defaults) the server, after the common prefix, walks the held prompt and
the new one together: a run of at least *N* tokens that matches is shifted into its new position and
counted as reused, and on a miss the **held** cursor advances by one — the new prompt's cursor never
does. So the tokens that follow a trim, which sit verbatim later in the held prompt, are found and
shifted; the tokens that follow an inserted summary are never reached, because the summary's own
tokens match nothing in the held prompt and hold the walk at that position until the held prompt runs
out. A prompt wholly reused still has one token evaluated (3414). `prefix_mortality.slotsim.
cache_reuse_walk` is that walk, over the stored token lists; `summarize_m5` recomputes *d*, the walk
and the prediction from the stored tokens and refuses a record that carries another value or another
chunk list.

**What decides.**

| case | rule |
|---|---|
| A trial matches. | The compacted request's reuse equals its prediction; both requests' two counts add up to their token counts and their two reuse fields agree. |
| `HELD` | Every counted trial of both models matches. Each hypothesis is decided on its own runs. |
| `NOT CONFIRMED` | At least one counted trial does not match. The results entry states every mismatching trial with *d*, the chunks and the reading. |
| A control fails. | The full request reuses more than its header; the compacted request's bytes equal the full one's; a record lies between them; the stored prediction or chunk list differs from the recomputation. The run stops, and no verdict follows from it. |
| NOT MEASURABLE | The server does not report a field or a slot context; a request has at least as many tokens as the slot context; the local date changed inside a trial. The verdict stays `unresolved`. |
| The records say another number of slots, more than one slot context, an arm or a conversation not registered, or a corpus other than the vendored one. | The run is not that experiment. |

**Known before the run.**

| fact | consequence |
|---|---|
| The server does not report `--cache-reuse`. | The run script passes it; the records read it back only through the walk's result, as 0019 reads the idle timer through `is_sleeping`. A `C` run whose compacted requests reuse only *d* would be a server without the flag or a walk read wrongly, and would be a mismatch. |
| Four unrecorded requests were sent before this entry, on 2026-10-11: `qwen` under `--parallel 1 --cache-reuse 256`, conversation 12, both arms. | Nothing from them is evidence and no figure from them appears here. |
| `--cache-reuse` needs a memory that can shift (`llama_memory_can_shift`); the server logs a warning and ignores the flag otherwise. | Both models have standard attention; a `C` run reading only *d* throughout would be reported as such, with the server log read. |
| The `D` cell's compactions all leave *d*/*n* far above 0.10 (the head alone is about 4,800 of some 10,000 tokens). | `H-M5LD` re-measures 0010's rule at this scale and is expected to read *d*; it is registered because the claim "a compaction costs you everything after it" is what harness authors act on, and the price under the defaults is what they pay. |
| The longest conversation is about 16,000 tokens in full; the records carry contexts of 40,960 and 50,944. | Every request fits. |

**Status.** `H-M5L1`, `H-M5LD` and `H-M5LC` are `[STRETCH]`: registered, not run. `qwen` runs first.
### 0040 — 2026-10-11 — Model switch and restart registered on llama.cpp: H-M6LA, H-M6LB, H-M6LR

prior-entries-sha256: 782831a4d12df600cc7e70512c31cdfab1f56e7bf409c50fc985a34799f56479

**Registers** `config/m6.toml`, now `registered_by = "0040"`, and three hypotheses. Engine, child A's
models and the machine are those of 0002; the request parameters those of `config/controls.toml`, the
bodies carrying a `model` field that names the child. Child B is a second, small model pinned in
`config/m6.toml` — `unsloth/Qwen3-1.7B-GGUF` `Qwen3-1.7B-Q4_K_M.gguf`, a third-party conversion of the
owner's weights (the owner's repository ships Q8_0 only), sha256 the Hub's LFS digest at revision
`d7f544ee`, read 2026-10-11 — because `config/engines.toml` is sealed by the hashes in its records.
Ruled by the operator on 2026-10-11: both 8B families as child A; this Q4_K_M as child B; one
registering and one results entry per experiment.

**Id.** `M6` is the sixth cause of 0001, model switch; `A` and `B` are the router with four and with
one child allowed, `R` a restart of a single server (ruled 2026-10-06 §9: the redeploy a client meets
is the process event, so it is a registered cell and not a probe).

| id | server | a trial | predicted reuse |
|---|---|---|---|
| `H-M6LA` | Router (`--models-dir`, a preset giving every child `ctx-size 16384`, `--models-max 4`), A and B loaded before the trial. | The base request to A; its messages to B; the anchor's bytes to A. | A: at most the tokens before its nonce (a control); B: the same; A again: *n*_A − 1. |
| `H-M6LB` | The same with `--models-max 1`. | The same. | A and B as above; A again: 0. |
| `H-M6LR` | One server, child A alone, `--parallel 1 --slot-save-path`. | (i) anchor; stop, start; resend. (ii) a fresh anchor; `POST /slots/0?action=save`; stop, start; `action=restore`; resend. | (i) 0; (ii) *n* − 1. |

Three repetitions per cell per family: 9 requests per router run, 8 per restart run with four
restarts. Child A's records must say 4 slots (router) or 1 slot (restart) and a slot context every
request fits.

**The reading** (`tools/server/server.cpp` 205–248; `server-models.cpp` 264–384, 1074–1090,
1931–1960, 2025–2075; `server-context.cpp` 4784–4811, 5304–5315, 2606–2665 at the pin). The router
forwards a completion, a render (`/apply-template`), a tokenization and a slot action to the child
the body's `model` names, loading it first when it is not running; `GET /props?model=NAME` is
forwarded, `GET /models` lists every child with its status. A child is another process with its own
slots and prompt cache: it has never seen a prompt sent to its sibling. A child that was switched away
from keeps its slots as long as it stays loaded; with `--models-max N` the router unloads the least
recently used idle child when an (N+1)-th must load, and a child loaded again is a fresh process. So a
model change ends the match for the request that changed — and not for the next request that changes
back, while the child lives; `--models-max 1` is the case where it does not. A restart is the same event
for a single server: every slot and the prompt cache are gone. `action=save` writes the slot's tokens
and KV state to a file under `--slot-save-path`; `action=restore` after the restart reads them back into
the slot, and the resend is an identical resend into a held slot, *n* − 1 (0003).

The driver (`prefix_mortality.m6`) starts and stops the server itself, from the command line the run
script gives it, and records what it can observe of the process — a generation number, a pid and a
start time — never the command line. Before each router request it records the loaded set from `GET
/models`, and each record carries the child's `/props` and the name the response reports.

**What decides.**

| case | rule |
|---|---|
| A trial matches. | The resend's reuse equals its prediction; every request's two counts add up to its token count and its two reuse fields agree. |
| `HELD` | Every counted trial of both families matches. Each hypothesis is decided on its own runs. |
| `NOT CONFIRMED` | At least one counted trial does not match. The results entry states every mismatching trial with the loaded set, or the generations, it recorded. |
| A control fails. | The anchor, or B's request, reuses more than its header; the resend is not the anchor's bytes; a record lies between the trial's requests; a response names a child other than the one asked; the loaded set is not what the cell requires (A and B loaded at the resend under `--models-max 4`; A not loaded, at most one child loaded, under `--models-max 1`); the generation did not rise by one across a restart; the save or the restore reports a count other than the anchor's. The run stops, and no verdict follows from it. |
| NOT MEASURABLE | Child A does not report a field or a slot context; a request has at least as many tokens as that context; the local date changed inside a trial. The verdict stays `unresolved`. |
| The records say another number of slots for child A, more than one slot context, a part or a repetition not registered. | The run is not that experiment. |

**Known before the run.**

| fact | consequence |
|---|---|
| Ten unrecorded requests were sent before this entry, on 2026-10-11, child A `qwen`: 4 under the restart cell (both parts), 3 under each router cell. Two earlier router attempts sent no request: the driver read the loaded set before the child had come up, and was corrected to wait for `loaded` (the router reports `loading` for about ten seconds). A router was also started once with no request sent, to read `GET /models` and `/props?model=`. | Nothing from them is evidence and no figure from them appears here. |
| The router forwards a render or a tokenization to the child named, loading it if needed. | Every trial's bodies are rendered and tokenized before its first request is sent, so under `--models-max 1` the loads the preparation causes precede the anchor; between the anchor, B's request and the resend nothing but those three requests is sent, and the loaded set each record carries says so. |
| B's prompt is B's own render of the anchor's messages. For `qwen` the render is the same text (the same template family); for `llama` it differs. | B reuses nothing either way: it is another process. Its reuse is a control, not a result. |
| The children's context is set by the preset to 16,384; the base request is about 4,900 tokens. | Both children fit the machine beside each other (memory read at the probe: 85% free after the run); every request fits. |
| The restart cell's saved state is about 700 MB per save and is deleted with the run's results folder; the restore reports the token count read back. | The records carry the counts, not the file. |
| Not measured: a LoRA change (no adapters here); eviction of a child under queue pressure; a switch while the child is busy. | Stated in the results entry as what the runs do not show. |

**Status.** `H-M6LA`, `H-M6LB` and `H-M6LR` are `[STRETCH]`: registered, not run. `qwen` runs first.
### 0041 — 2026-10-12 — H-M8L1 and H-M8LD held: the slot policy prices every turn of 50 conversations

prior-entries-sha256: e45b5b8a38c007fefee52e8df24fd3a6314ed66d42707beca51533af5027a9ba

verdict: H-M8L1 = HELD

verdict: H-M8LD = HELD

**Outcome** `[BASELINE]`. Seven runs registered by 0038 were made at commit `5531078` (the M8 code is
that of `cd9a471`; `config/m8.toml` is byte-identical at both), the server started fresh for each.
Their records and requests are committed with this entry. Every figure below is from `summarize_m8
--run` on those files, or from the `server` field of the records.

| run | model | C | requests | counted, matching | near | deaths | cache searched, restored, evicted |
|---|---|---|---|---|---|---|---|
| `20261012T012934Z…` | qwen | 1 | 762 of 762 | 762, 762 | 0 | 0 | 19, 0, 13 |
| `20261012T014430Z…` | llama | 1 | 762 of 762 | 762, 762 | 0 | 0 | 9, 0, 4 |
| `20261012T020157Z…` | qwen | 2 | 90 of 90 | 90, 90 | 0 | 48 | 35, 25, 0 |
| `20261012T021306Z…` | llama | 2 | 90 of 90 | 90, 90 | 0 | 54 | 25, 19, 0 |
| `20261012T024929Z…` | qwen | 6 | 188 of 188 | 188, 188 | 0 | 115 | 76, 60, 1 |
| `20261012T031552Z…` | llama | 6 | 188 of 188 | 188, 188 | 0 | 132 | 47, 35, 0 |
| `20261012T154555Z…` | qwen | 12 | 297 of 297 | 294, 294 | 3 | 213 | 93, 64, 11 |

All seven: outcome ALL MATCH; no failed control, no unmeasurable field; one local date per run;
records say 1 slot (C = 1) or 4 slots (C > 1), slot context 40,960 (qwen) or 50,944 (llama); engine
`b11235-6c7a87f7e`. The three `near` requests of the C = 12 run are cache comparisons the policy
decided by one token (entries 0, 1 and 3 of the cache against the slot's own prompt, at
conversations 12 turn 16, 4 turn 17 and 10 turn 18); they are reported and not counted, as 0038
states.

**Verdict.** Every counted request of every run matches the prediction of the pinned server's slot
and prompt-cache policy over the stored token lists: 2,374 requests, including 562 deaths and the
restores and evictions along the way. By the rule of 0038, `H-M8L1` is `HELD` and `H-M8LD` is
`HELD`. One registered run was not made: see below.

**What the runs measure.** The share of each run's tokens served from a held prefix, and where the
prefix died.

| | qwen | llama |
|---|---|---|
| C = 1, one slot: share over 762 requests | 0.9593 (per conversation 0.8341 to 0.9799) | 0.9667 (0.8392 to 0.9825) |
| C = 1: first request of every conversation after the first | 4,830 reused — the system text, the tools and the greeting, held from the previous conversation | 5,615 |
| C = 2 (tasks 12, 44): share, deaths | 0.8258, 48 of 90 | 0.8111, 54 of 90 |
| C = 6 (+18, 10, 23, 14): share, deaths | 0.7757, 115 of 188 (per conversation 0.6079 to 0.8850) | 0.7590, 132 of 188 (0.6264 to 0.8604) |
| C = 12 (+24, 48, 7, 32, 4, 21): share, deaths | 0.7347, 213 of 297 (0.6079 to 0.8850) | not run (below) |
| tokens lost per death, C > 1: median, largest | about 2,500; 8,227 | about 2,900; 7,395 |

At one slot no conversation ever died: each turn extended the held prompt and reused all of it, and
the only loss was the 3 to 17 per cent of each conversation that is its own new text. Interleaved,
the conversations killed each other on most turns — a request found the other conversation's prompt
in the slot, kept more than half of it (the 4,800-token head), and so the policy neither searched the
cache nor restored its own state; the request paid for its whole history again. The cache was searched
only when a conversation had grown past twice the head (f_keep below 0.5), and then usually restored
its own state (60 of 76 searches at C = 6 on qwen). Evictions from the 8192 MiB cache appeared once at
C = 6 and eleven times at C = 12, where the states of twelve conversations of 5,000 to 16,000 tokens no
longer fit; each eviction was predicted by the registered geometry and matched.

**The run not made.** The llama C = 12 run was refused before its first request was sent, and recorded
nothing: the request store (`corpus/requests/`, one file per request body) already held that body's
render from 2026-10-11, and the render of the same bytes on 2026-10-12 differs — Llama 3.1's chat
template writes the day's date into the system header, and M8's bodies carry no nonce, so the first
request of every conversation (the system text and the tools alone) is byte-identical across
conversations and across days. The store refuses a second render for the same bytes, as it must. One
unrecorded render was made on 2026-10-12 to confirm the difference: one line, `Today Date: 11 Oct 2026`
against `12 Oct 2026`, over 30,005 characters. Qwen's template carries no date, so its C = 12 run on
2026-10-12 shared the store without conflict. `H-M8LD` is therefore decided on five runs, three on
qwen and two on llama; a llama run at C = 12 under this registration can be made only on 2026-10-11,
which is to say never. Making one needs an amendment that registers a fixed `date_string` for Llama's
template, and the operator's ruling on whether the cell is wanted; until then the C = 12 regime —
evictions from the cache — is measured on one model.

**Known limits.** Requests in flight together, conversations other than the vendored fifty, and a
cache size other than the default were not measured (0038). The `near` margin excluded 3 of 2,377
requests. The seven runs took 12 to 38 minutes each; the C = 12 run's longer requests re-prompted up
to 16,000 tokens after a death.

**Status.** `H-M8L1` and `H-M8LD` are `[BASELINE]`, no refuter yet. Six causes are measured on this
engine: edit position, serialization drift, templating, idle expiry, eviction, and now lifespan along
real conversations; rebuild (0039) and model switch (0040) are registered and run next.
### 0042 — 2026-10-12 — H-M5L1, H-M5LD and H-M5LC held: a trim is shifted whole, a summary costs everything after it

prior-entries-sha256: 93d3033d35d49788f9caecde0a6d76c8d9761f92332b9d118ee3b0241cbf4c58

verdict: H-M5L1 = HELD

verdict: H-M5LD = HELD

verdict: H-M5LC = HELD

**Outcome** `[BASELINE]`. The six runs registered by 0039 were made at commit `819fd22` (the M5 code
is that of `5531078`, which registered it), one per hypothesis per model, the server started fresh for
each. Their records and requests are committed with this entry. Every figure below is from
`summarize_m5 --run` on those files, or from the `server` field of the records.

| run | model | server | trials counted, matching | near the threshold |
|---|---|---|---|---|
| `20261012T162735Z…` | qwen | `--parallel 1` | 20, 20 | 0 |
| `20261012T164445Z…` | llama | `--parallel 1` | 20, 20 | 0 |
| `20261012T165720Z…` | qwen | defaults | 20, 20 | 0 |
| `20261012T171426Z…` | llama | defaults | 20, 20 | 0 |
| `20261012T172656Z…` | qwen | `--parallel 1 --cache-reuse 256` | 20, 20 | 0 |
| `20261012T174145Z…` | llama | `--parallel 1 --cache-reuse 256` | 20, 20 | 0 |

All six: outcome ALL MATCH; no failed control, no unmeasurable field; one local date per run;
records say 1 slot or 4 slots as the hypothesis requires; slot context 40,960 (qwen) or 50,944
(llama); engine `b11235-6c7a87f7e`. Ten conversations (tasks 12, 44, 18, 10, 23, 14, 24, 48, 7,
32), full requests of 9,829 to 16,276 tokens (qwen) and 9,949 to 15,655 (llama), compacted requests of
7,327 to 14,912 and 7,672 to 13,962.

**Verdict.** Every trial of every run matches: the compacted request reused exactly what the
hypothesis's rule predicts from the two stored token lists. By the rule of 0039, `H-M5L1`, `H-M5LD`
and `H-M5LC` are `HELD`.

**The same compaction, priced three ways.** *d* — the tokens the compacted request shares with the
full one from the start — is the head: the system text, the tools, the greeting and the first user
message, 4,872 to 4,880 tokens on qwen and 5,646 to 5,656 on llama, between 0.33 and 0.74 of the
compacted request, far above the 0.10 threshold in every trial.

| server | `trim` (early turns removed) | `summary` (early turns replaced by one message) |
|---|---|---|
| `--parallel 1` | reuses *d*; recomputes the whole kept tail: 2,455 to 9,992 tokens (qwen), 2,025 to 8,269 (llama) | reuses *d*; recomputes the summary and the tail |
| defaults | the same, *d* above the threshold in all 20 trials per model | the same |
| `--parallel 1 --cache-reuse 256` | **reuses everything but one token** (*n* − 1 in 10 of 10 trials per model): the walk found the kept tail later in the held prompt and shifted it whole, one chunk of 2,455 to 9,992 tokens (qwen) and 2,025 to 8,269 (llama) | reuses *d*: nothing shifted in 10 of 10 trials per model — the summary's tokens match nothing in the held prompt, and the walk never advances past a token of the new prompt it cannot match |

The one engine mechanism that can save a compaction, `--cache-reuse`, saves the trim completely and
the summary not at all; and it is off at the defaults. The price of a compaction at the defaults is
everything after the cut, on both models.

**Controls.** The full request reused at most its header in all 120 trials: on qwen 0 to 6 tokens of a
header of 29 to 37; on llama 0 or 3,911 to 3,912 of a header of 3,924 to 3,934 — with
`tools_in_user_message: false` Llama's template renders the tools before the system text, so the nonce
follows the tool schemas, which the previous trial's prompt shares; the bound is 0002's definition and
holds. At the defaults the qwen full requests reused 0 (the least recently used slot, 0005) and the
llama ones 3,911 (the held slot, chosen by a similarity of 0.39, keeping the tools).

**Known limits.** Not measured: compactions at a cut other than the midpoint; a summary written into
the system text rather than a user message; `--cache-reuse` with a chunk size other than 256; a
server that cannot shift its memory (both models here can, and no warning appears in the server
logs, which are not committed). The compaction bodies carry a nonce (0039): these are trials, as
M1's, not the no-nonce replay of M8.

**Status.** `H-M5L1`, `H-M5LD` and `H-M5LC` are `[BASELINE]`, no refuter yet.
### 0043 — 2026-10-12 — H-M6LA, H-M6LB and H-M6LR held: a model change ends the match for one request; a restart ends everything; a saved slot survives it

prior-entries-sha256: e5a8c85438699de5847b6f50dbb9df7c3d8d82a0956e5f606d9b64f04c7b4022

verdict: H-M6LA = HELD

verdict: H-M6LB = HELD

verdict: H-M6LR = HELD

**Outcome** `[BASELINE]`. The six runs registered by 0040 were made at commit `819fd22` (the M6 code
is that of `5531078`, which registered it), one per hypothesis per family, the driver starting and
stopping the servers itself. Their records and requests are committed with this entry. Every figure
below is from `summarize_m6 --run` on those files, or from the `server` field of the records.

| run | child A | server | trials counted, matching |
|---|---|---|---|
| `20261012T175203Z…` | qwen | `--parallel 1 --slot-save-path` | 6, 6 |
| `20261012T175324Z…` | llama | `--parallel 1 --slot-save-path` | 6, 6 |
| `20261012T175501Z…` | qwen | router, `--models-max 4` | 3, 3 |
| `20261012T175537Z…` | llama | router, `--models-max 4` | 3, 3 |
| `20261012T175618Z…` | qwen | router, `--models-max 1` | 3, 3 |
| `20261012T175723Z…` | llama | router, `--models-max 1` | 3, 3 |

All six: outcome ALL MATCH; no failed control, no unmeasurable field; one local date per run; child A
reports 1 slot (restart) or 4 slots (router) and a slot context of 40,960 (qwen) or 50,944 (llama)
alone, 16,384 for every child under the router's preset; engine `b11235-6c7a87f7e`; child B
`qwen17q4`, every response naming the child asked.

**Verdict.** Every trial of every run matches. By the rule of 0040, `H-M6LA`, `H-M6LB` and `H-M6LR`
are `HELD`.

**What the trials read.** Anchors of 4,866 to 4,872 tokens (qwen) and 5,643 to 5,652 (llama).

| cell | B's request | A again, or the resend | the loaded set before the resend |
|---|---|---|---|
| router, four children allowed | 0 in 6 of 6 | *n* − 1 in 6 of 6 (4,865 to 4,871; 5,643 to 5,645) | A and B, in every trial |
| router, one child allowed | 0 in 6 of 6 | 0 in 6 of 6 | B alone, in every trial: loading B unloaded A, and the resend reloaded A into a fresh process |
| restart, bare | — | 0 in 6 of 6 | — |
| restart, slot saved before and restored after | — | *n* − 1 in 6 of 6 (4,871, 4,865, 4,871; 5,651, 5,649, 5,648) | — |

The process generation rose by one across every restart (1 to 7 over each restart run); every save
and restore reported the anchor's token count. Every anchor reused at most its header: 0 under the
router (a fresh or an empty slot), 0 to 5 (qwen) and 0 to 32 (llama) at one slot, the header shared
with the previous trial's prompt.

So the README's sentence — a model change kills the prefix — is true for exactly one request: the
one that changed model, which another process answers. The request that changes back finds its slot
alive as long as its child stayed loaded, and reads 0 only when the router had to unload it
(`--models-max 1`). A restart of the serving process ends every held prompt and the prompt cache with
it; a slot saved to disk before the restart and restored after is an identical resend into a held
slot, *n* − 1 (0003).

**Known limits.** Not measured: a LoRA change (no adapters here); eviction of a child under queue
pressure rather than `--models-max`; a switch while the child is busy; a restart under the defaults
(four slots) rather than one. B's reuse is a control, not a result: for `qwen` B's render is the same
text as A's (the same template family), for `llama` it differs, and B reused nothing either way. The
save files (about 700 MB each) are not committed; the records carry the counts the server reported.

**Status.** `H-M6LA`, `H-M6LB` and `H-M6LR` are `[BASELINE]`, no refuter yet. With this entry every
cause of 0001 is measured on llama.cpp: edit position, serialization drift, templating, idle expiry,
rebuild, model switch, eviction by intervening requests, and lifespan along real conversations.
### 0044 — 2026-10-12 — Lifespan on Llama with the template's date pinned: config/m8l.toml registered

prior-entries-sha256: 1488f58bd728576d99fef8c6f556c7d0fba5eb4985ccaf10690bea851ca1ead6

**Registers** `config/m8l.toml`, now `registered_by = "0044"`, for the hypotheses `H-M8L1` and
`H-M8LD` of 0038 on the `llama` family. It is `config/m8.toml` in every value but one: Llama's
template arguments gain `date_string = "11 Oct 2026"`. No new hypothesis; the same ids, rules,
corpus, constants and policy. `config/m8.toml` is sealed by the hashes in its records and does not
change; a record written under this file names it (`config: m8l`) and hashes it under that key, and
`summarize_m8 --config m8l` reads it.

**Why.** 0041 could not make the llama C = 12 run: Llama 3.1's chat template writes the current date
into the system header, M8's bodies carry no nonce, so the first request of every conversation — the
system text and the tools alone — is byte-identical across conversations and across days, and the
request store, which holds one render per request body, refused the 2026-10-12 render of a body it
had stored with the 2026-10-11 render. `date_string` is the argument Llama's template takes for that
line. Pinning it makes the render independent of the day the run is made, so runs under this file
can be made on any day and share the store among themselves. It is pinned to the local date of
0041's llama runs so that the prompts the engine sees are, byte for byte, the prompts those runs sent.

**What this changes in the replay.** Nothing the policy sees. The argument travels in the request
body, so every body under this file differs from 0041's llama bodies by that field and is stored
under its own hash — about a thousand new request snapshots, each carrying `date_string` — while its
rendered prompt and token list are identical to the earlier run's for the same turn. Qwen's template
takes no date and is not affected; this file registers nothing new for `qwen`.

**What runs.** All four llama cells of 0038 under this file — `H-M8L1` (C = 1) and `H-M8LD` at
C = 2, 6 and 12 — so that the llama half of both hypotheses is one set under one configuration, made
on one day; the results entry states that these four runs supersede 0041's three llama runs for the
llama half, and that the earlier runs stand as made. Ruled by the operator on 2026-10-12: the clean
single set rather than the one missing run.

**What decides.** 0038's table, unchanged; the summarizer refuses a record that names another config
or hashes to another file.

**Known before the run.**

| fact | consequence |
|---|---|
| The pinned date is a Llama template argument, not a server setting. | `qwen` runs are unaffected; the records of a llama run under this file show `date_string` in every stored body. |
| A run under this file on a day other than 2026-10-11 renders `Today Date: 11 Oct 2026`. | That is the intent: the prompt is the one the store holds. A reader of the records sees the pinned date in the render, not the day of the run; the record's `local_date` and timestamps carry the day. |
| No request under this file has been sent before this entry. | The four runs are the first. |
| The collision itself is a templating death the client never caused: a Llama conversation whose requests straddle midnight loses its whole prefix, because the template re-dates the header. | Not measured here; noted as a candidate cell. |

**Status.** `config/m8l.toml` is registered; `H-M8L1` and `H-M8LD` keep their verdicts of 0041
(`HELD`, `[BASELINE]`) pending the four runs and the results entry.
### 0045 — 2026-10-12 — 0041, 0042 and 0043 survived a refuter: eleven hypotheses [VALIDATED]; three figures corrected

prior-entries-sha256: 10ead15dd10b3a73c6b878c00564423c22bccf99fdb1478bba244fcfa177f8c6

**Under rule 5** (entry 0008). The results of 0041, 0042 and 0043 were given to a tenth refuter,
independent of the author as in 0010, 0011, 0014, 0018, 0021, 0024, 0027, 0034 and 0037: a separate
session with no access to the one that produced the code and the entries, nor to the earlier
refuters' work.

| | |
|---|---|
| what it read | An export of commit `3e456ae`, the whole tree, and the two server source files at the pinned llama.cpp commit by address. It read all 2,377 M8 records, 240 M5 records and 60 M6 records with their stored requests, recomputed every figure with its own code — including its own implementation of the slot and prompt-cache policy from the cited source lines, written before it opened `slotsim.py` — and imported nothing from the package. Denied git, it verified internal consistency of the records, not that the runs happened as described; it could not re-contact the servers. |
| the brief | Re-implement the policy and the `--cache-reuse` walk from the source; recompute every prediction, every control and every figure of the three entries from the stored tokens; check the schedules against the vendored corpus; recompute the chain lines; attack the controls and the prose. |
| verdict | All eleven: NOT REFUTED. "All eleven HELD verdicts survive full recomputation from raw bytes. Three prose figures are wrong but none is load-bearing." |

**What it tried and what survived**, from its report.

| tried | found |
|---|---|
| The policy, re-implemented from the source. | Every stored prediction and every intermediate reading of the policy reproduce for all 2,377 M8 requests; the reading equals the prediction in all 2,374 counted requests and in the 3 `near` ones too. Searched, restored and evicted counts, deaths, shares, per-conversation ranges, first-request reuse and the largest losses all as tabled. |
| The schedules. | From the vendored corpus (hash equal to its provenance): file order for C = 1; the C longest by assistant turns, ties by task id, for C > 1. Every record's conversation, turn and body match. |
| The walk, re-implemented. | Predictions, chunk lists and shifted counts reproduce in all 120 M5 trials; the reading equals the prediction in 120 of 120; the full request within its header in 120 of 120. |
| The process cells. | Resend bytes equal the anchor's, one nonce, consecutive records, loaded sets as each cell requires, every response from the child asked, generations rising by one across each restart, save and restore counts equal to the anchor's, in all 24 M6 trials. |
| The chain. | 0041, 0042 and 0043 reproduce from the normalized entries section. |
| The refusal of 0041. | The store holds the first-turn body with `Today Date: 11 Oct 2026` in its render, referenced by all three llama runs, and no 12 October render of a nonce-free body; the refusal itself left no record and is, as 0041 says, unverifiable from the tree. |
| Its strongest counter-cases. | (1) The `near` margin flags a decision within one token of a threshold but not an exact tie in the cache's strict comparisons; 153 counted requests were decided by such a tie, and all 153 matched — the strict reading of the source is corroborated, and a tie-inclusive margin would have counted fewer requests, not changed a verdict. (2) A real KV state carries metadata beyond tokens × geometry; all 29 evictions matched regardless. (3) The defaults of four server flags are not in the two source files it fetched; 575 interleaved requests match only under cleared idle slots, which supports the reading empirically. |

**Corrections.** Three sentences overstate or round wrongly; the entries are immutable and are
corrected here, in the form of 0034.

| entry | sentence | corrected, from the committed records |
|---|---|---|
| 0042 | The llama full requests reused "0 or 3,911 to 3,912 of a header of 3,924 to 3,934", and at the defaults "3,911 (the held slot, chosen by a similarity of 0.39, keeping the tools)". | They reused 0 or 3,910 to 3,912: at one slot 5 × 3,910, 12 × 3,911, 2 × 3,912; at the defaults 13 × 3,910 and 6 × 3,911; under `--cache-reuse` 11 × 3,910 and 8 × 3,911; the similarity by which the held slot was chosen ranged from 0.25 to 0.39. The bound and the verdicts are unaffected. |
| 0041 | Tokens lost per death on llama, "median about 2,900". | The pooled median over the 186 llama deaths is 2,550 (per run 2,362 at C = 2 and 2,875 at C = 6); 2,888 is the mean. Qwen's 2,511 stands. |
| 0038 | "3 to 52 assistant turns per conversation". | 6 to 52. |

**Consequences.** `H-M8L1`, `H-M8LD`, `H-M5L1`, `H-M5LD`, `H-M5LC`, `H-M6LA`, `H-M6LB` and `H-M6LR`
are `[VALIDATED]`: twenty-seven validated hypotheses across two engines, and every cause of 0001
measured and refuter-checked on llama.cpp. The validation covers the runs 0041 made; the llama runs
under `config/m8l.toml` (0044) are pending and will be decided and, if the operator rules so,
refuted on their own.
### 0046 — 2026-10-12 — What the server does not report: the parameters that priced every death, read back from behaviour

prior-entries-sha256: 7307fe323123e4558624c817805325ca31cd3672ea788191fee438d7d814cfd9

**Descriptive.** No run, no hypothesis, no verdict. This entry collects, from the entries that
measured them, the server-side parameters that decided the reuse of every request on this ledger
and that no client can read from either server's self-description. In every case the registering
entry records the same sentence: the run script passes the value, and the records read it back only
through the behaviour it produces. The committed records are the evidence; this entry is their index.

**On llama.cpp `b11235`.** `GET /props` reports the build, the number of slots, the slot context
and, since 0019, `is_sleeping`. It does not report:

| parameter | default | what it decided | how the records recovered it |
|---|---|---|---|
| `--slot-prompt-similarity` | 0.10 | which slot a request takes, and so whether an early edit reads its position or 0 (0010: the 0.10 cliff, bracketed at 0.0929–0.1086 across models, 0.0950/0.1044 on the third family, 0031); whether an interleaved conversation finds its own state or the shared head (0041) | the cliff's position in the edited requests' reuse; the policy's slot choice in 2,377 replayed requests |
| `--cache-ram` | 8192 MiB | how many foreign prompts a held state survives (0013: the twelfth intervening prompt ends the prefix); when interleaved conversations' states are evicted (0041: 11 evictions at C = 12) | "8192 MiB is read, not recorded" (0012); the cliff's K and the eviction sites, each predicted by the registered geometry |
| `--cache-idle-slots`, `--kv-unified` | on | that every idle slot is saved and cleared when a request launches, so a fresh-nonce prompt reuses 0 at the defaults (0005) and only one slot ever holds a prompt (0041) | the server's own log in an unrecorded trace (0005); 575 interleaved requests that match only under cleared idle slots (0045) |
| `--sleep-idle-seconds` | −1, off | the one timer: nothing expires by time at the defaults; a server with the flag loses everything past the threshold (0020) | `is_sleeping` after each gap, which `/props` does report; the flag itself is passed by the run script (0019) |
| `--cache-reuse` | 0, off | whether a trimmed context is shifted whole or recomputed (0042: *n* − 1 against *d*) | the walk's result in the compacted requests' reuse (0039) |
| `--parallel` | auto, 4 here | one slot versus four: exact reuse versus the threshold cliff (0010) | `total_slots`, which `/props` does report — the one policy parameter a client can read |

**On vLLM `b6d8e8af` (CPU backend).** `GET /version` reports the version string; `GET /v1/models`
the served name. Neither reports:

| parameter | default | what it decided | how the records recovered it |
|---|---|---|---|
| `--block-size` | 128 on this backend (16 on GPU, refused here) | the price of every death: cached = floor(min(*d*, *n* − 1)/*B*)·*B*, created the complement (0026, 0036); the same edit costs up to *B* − 1 more than llama.cpp's exact reuse (0033) | "the records read it back only through the block arithmetic of the readings" (0022); at prompt lengths where *n* mod 128 < 32 the controls cannot discriminate 32 from 128 at all (0023); 57 of 65 trials per run discriminate it (0026) |
| `VLLM_CPU_KVCACHE_SPACE` | 4 GiB here | the cache's capacity, which no run on this ledger reached | passed by the run script, recorded from the script, not from the server |

**What this means for a client.** The ledger's two engines agree on where a prefix dies — the first
differing token, placed within nonce jitter at the same position on both (0032) — and disagree only
on the price (0033, 0036). The price is set by the parameters above. A client that computes its own
reuse from `cached_tokens` or `cache_n` can tell *that* it lost tokens and *where*; it cannot tell
*why* without the number the server did not publish, and it cannot predict the price of the next
request. Every prediction this ledger made and every refuter checked rested on values read from the
server's source and command line, not from the server. Exposing them — the block size on vLLM's
`/version` or model listing; the cache size, the similarity threshold, the cache-reuse chunk, the
idle-slot flags and the timer on llama.cpp's `/props` — would make the price of a prefix observable
to the client paying it. This is the one feature the ledger's evidence asks for; it is stated here as
a reading of the record, and any request upstream is the operator's to make.

**Known limits.** The defaults quoted are those of the pinned commits, read from their sources
(0002, 0012, 0019, 0022, 0039); other versions may differ. `GET /slots` on llama.cpp
was not read for per-slot state. The vLLM lane ran one model family and one backend.
### 0047 — 2026-10-12 — H-M8L1 and H-M8LD held on Llama under the pinned date: four runs, 1,337 of 1,337 match; the llama half is one set

prior-entries-sha256: 468ce415131feb67ae0b1071742577a980c208d1dfc2812fe39823713f4a9a9a

verdict: H-M8L1 = HELD
verdict: H-M8LD = HELD

**Outcome.** The four llama runs registered by 0044 were made at commit `650a165` under
`config/m8l.toml`, one after another on one day, the server started fresh for each. Their records
and 713 new request snapshots are committed with this entry. Every figure below is from
`summarize_m8 --run … --config m8l` on those files, run on both machines with identical output, or
from the `server` field of the records.

| run | C | requests | counted, matching | near | deaths | cache searched, restored, evicted |
|---|---|---|---|---|---|---|
| `20261012T185003Z…` | 1 | 762 of 762 | 762, 762 | 0 | 0 | 9, 0, 4 |
| `20261012T185937Z…` | 2 | 90 of 90 | 90, 90 | 0 | 54 | 25, 19, 0 |
| `20261012T190937Z…` | 6 | 188 of 188 | 188, 188 | 0 | 132 | 47, 35, 0 |
| `20261012T193250Z…` | 12 | 297 of 297 | 297, 297 | 0 | 229 | 48, 35, 0 |

All four: outcome ALL MATCH; no failed control, no unmeasurable field; one local date per run
(2026-10-12); every record names `config: m8l` and hashes `config/m8l.toml` to one value; every
stored body carries `date_string = "11 Oct 2026"`; records say 1 slot (C = 1) or 4 slots (C > 1),
slot context 50,944, engine `b11235-6c7a87f7e`.

**Verdict.** Every request of every run matches the prediction of the pinned server's slot and
prompt-cache policy over the stored token lists: 1,337 requests, 415 deaths, no `near` exclusion.
By the rule of 0038, `H-M8L1` is `HELD` and `H-M8LD` is `HELD`.

**These four runs are the llama half.** As 0044 states, they supersede 0041's three llama runs for
the llama half of both hypotheses; the earlier runs stand as made. The supersession costs nothing:
for C = 1, 2 and 6 the new run's sequence of (conversation, turn, observed reuse, predicted reuse) is
identical, request for request, to 0041's run at the same C — the bodies differ by the one template
argument and are stored under new hashes, the rendered prompts and token lists do not, and the policy
is deterministic over them. The C = 12 run is the cell 0041 could not make.

**The C = 12 regime on Llama.** The table of 0041 gains its missing cell:

| | qwen (0041) | llama (this entry) |
|---|---|---|
| C = 12: share of tokens reused, deaths | 0.7347, 213 of 297 | 0.7454, 229 of 297 |
| per-conversation share | 0.6079 to 0.8850 | 0.6264 to 0.8604 |
| first request of each conversation after the first | 4,830 | 5,615 |
| cache searched, restored, evicted | 93, 64, 11 | 48, 35, 0 |
| tokens lost per death: median, mean, largest | about 2,500; —; 8,227 | 2,436; 2,630; 7,395 |
| tokens lost per death, all C > 1 runs pooled | median about 2,500 | 415 deaths: median 2,485, mean 2,746, largest 7,395 |

Twelve interleaved conversations killed each other on 229 of 297 turns on Llama as they did on
qwen, and the dead request reused the shared head — 5,630 to 5,635 tokens in every death — and paid
for the rest of its history again. Two things differ from qwen, both predicted. Llama's head is
longer (5,615 tokens against 4,830), so the policy's gate for searching the cache — the slot keeps
less than half of the new prompt — opens later in each conversation: 48 searches against 93. And
nothing was evicted: the registered geometry predicted no eviction from the 8192 MiB cache in this
run, and none occurred, where qwen's run evicted eleven times. The C = 12 regime is now measured on
both model families; the eviction regime remains measured on one.

**Known limits.** Those of 0038 and 0041: requests served one at a time, the vendored fifty
conversations only, the default cache size. The four runs took 9, 10, 23 and 32 minutes; the longest
prompt was 15,630 tokens. No run crossed a local midnight.

**Status.** `H-M8L1` and `H-M8LD` keep `[VALIDATED]` from 0045 on the evidence 0045 examined. The
llama C = 12 run is new evidence no refuter has seen and is `[BASELINE]` as a cell; the three
repeated runs add nothing a refuter has not already recomputed, since their reuse series are
0041's. Phase 1's planned runs are complete on both engines.
