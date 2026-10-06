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
| H-M4LD | On llama.cpp `b11235` at its defaults, a request identical to one served *g* seconds earlier, with nothing served between them, reuses *n* − 1 tokens at every registered *g* (0, 2, 4, 60, 600). | entry 0019 | unresolved |
| H-M4LS | On llama.cpp `b11235` started with `--sleep-idle-seconds 60`, the same request reuses *n* − 1 tokens after a gap of 20 seconds and 0 after a gap of 100 seconds, the server reporting sleeping in between. | entry 0019 | unresolved |

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
