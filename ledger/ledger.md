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
