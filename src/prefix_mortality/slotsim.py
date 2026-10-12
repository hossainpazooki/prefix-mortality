"""The pinned server's slot and prompt-cache policy, as a pure predictor.

Read at llama.cpp `6c7a87f` (tools/server/server-context.cpp 1558-1668 and 2447-2463,
server-task.cpp 1710-1775 and 1793-1830), not assumed. Fed the requests of a run in send order, with
what each response generated, it says what the next request reuses:

  * a request goes to the idle slot whose held prompt shares the largest fraction of the request
    (lcp / request length) above `similarity` (0.10 at the defaults); it is saved to and searched in
    the prompt cache ONLY if it would keep under half of that slot's prompt (f_keep < 0.5). With no
    slot above the threshold the least recently used slot is taken and the cache is always consulted;
  * saving a prompt is skipped when it is already a prefix of a cached one; it erases cached prompts
    that are prefixes of it; a state larger than the limit is not cached; the oldest entries go until
    the new one fits. One token's state is `bytes_per_token`; the sampled token has no KV cell and
    does not count;
  * a cached prompt replaces the slot's only if at least a quarter of it is kept AND it beats the
    slot's own prompt on both the kept fraction and the similarity, strictly; entries are tried in
    arrival order and a win raises the bar for the rest. Nothing better: the slot keeps its prompt;
  * the reuse is the common prefix of the slot's prompt and the request, capped at one below the
    request's length (a fully held prompt still has its last token processed);
  * after the request the slot holds the prompt, plus any generated token that was fed back as the
    input of a further decoding step; a slot that stops after its first sampled token is released
    without it (server-context.cpp 551 runs only for a slot that keeps generating), so with one token
    generated — the controls' max_tokens — the slot holds exactly the prompt. Every other idle slot is
    saved to the cache and cleared (`--cache-idle-slots` and `--kv-unified`, both on at the defaults).

`cache_reuse_walk` is `--cache-reuse N` (server-context.cpp 3262-3290): after the common prefix, a
greedy left-to-right walk over the held and new prompts, the held side advancing by one on a miss,
every matching run of at least N tokens shifted into place and counted as reused.

A token is (id, piece); a generated token fed back without a known id is (None, text) and equals a
token whose piece is that text. `near` names a decision made by one token or less; the summarizer
reports such a request and does not count it. This module imports nothing from the drivers or the
stand-ins.
"""
from dataclasses import dataclass, field

Token = tuple[int | None, str]


def _eq(a: Token, b: Token) -> bool:
    if a[0] is not None and b[0] is not None:
        return a[0] == b[0]
    return a[1] == b[1] and a[1] != ""


def lcp(a: list[Token], b: list[Token]) -> int:
    n, i = min(len(a), len(b)), 0
    while i < n and _eq(a[i], b[i]):
        i += 1
    return i


def tokens(ids: list[int], pieces: list[str]) -> list[Token]:
    if len(ids) != len(pieces):
        raise ValueError(f"{len(ids)} ids and {len(pieces)} pieces")
    return list(zip(ids, pieces))


def cache_reuse_walk(held: list[Token], new: list[Token], n_min: int) -> tuple[int, list[tuple[int, int, int]]]:
    """(n_past, chunks); a chunk is (position in the new prompt, position in the held prompt, length)."""
    n_past = lcp(held, new)
    chunks = []
    head_c = head_p = n_past
    while head_c < len(held) and head_p < len(new):
        n_match = 0
        while (head_c + n_match < len(held) and head_p + n_match < len(new)
               and _eq(held[head_c + n_match], new[head_p + n_match])):
            n_match += 1
        if n_match >= n_min:
            chunks.append((head_p, head_c, n_match))
            n_past += n_match
            head_c += n_match
            head_p += n_match
        else:
            head_c += 1
    return n_past, chunks


@dataclass
class Prediction:
    reuse: int
    slot: int
    by: str                      # "similarity" or "lru"
    f_sim: float | None
    f_keep: float | None
    cache_searched: bool
    saved: bool
    restored: bool
    erased: int
    evicted: int
    near: list[str] = field(default_factory=list)


class SlotSim:
    def __init__(self, slots: int, similarity: float = 0.10, cache_limit_bytes: int | None = None,
                 bytes_per_token: int = 1):
        if slots < 1:
            raise ValueError("a server has at least one slot")
        self.similarity, self.limit, self.bpt = similarity, cache_limit_bytes, bytes_per_token
        self.slots: list[list[Token]] = [[] for _ in range(slots)]
        self.last_used = [-1] * slots
        self.cache: list[list[Token]] = []
        self.requests = 0

    # --- the prompt cache -----------------------------------------------------------------------

    def _size(self, prompt: list[Token]) -> int:
        return sum(1 for t in prompt if t[0] is not None) * self.bpt

    def _cache_bytes(self) -> int:
        return sum(self._size(p) for p in self.cache)

    def _save(self, prompt: list[Token], near: list[str]) -> tuple[bool, int, int]:
        """server_prompt_cache::alloc. (saved, erased, evicted)."""
        if not prompt:
            return False, 0, 0
        for entry in self.cache:
            l = lcp(entry, prompt)
            if l == len(prompt):
                return False, 0, 0                     # already in the cache (a prefix of an entry)
        size = self._size(prompt)
        if self.limit is not None and size > self.limit:
            return False, 0, 0
        kept, erased = [], 0
        for entry in self.cache:
            l = lcp(entry, prompt)
            if l == len(entry):
                erased += 1                          # obsolete: a prefix of the saved prompt
                continue
            kept.append(entry)
        self.cache = kept
        evicted = 0
        if self.limit is not None:
            while self.cache and self._cache_bytes() + size > self.limit:
                self.cache.pop(0)
                evicted += 1
            if self.cache and self.limit - self._cache_bytes() - size < self.bpt:
                near.append("the cache fits the saved prompt by less than one token")
        self.cache.append(list(prompt))
        return True, erased, evicted

    def _load(self, slot: int, new: list[Token], near: list[str]) -> bool:
        """server_prompt_cache::load. True when a cached prompt replaced the slot's."""
        held = self.slots[slot]
        l_best = lcp(held, new)
        f_keep_best = l_best / len(held) if held else -1.0
        f_sim_best = l_best / len(new)
        found = None
        for idx, entry in enumerate(self.cache):
            l = lcp(entry, new)
            f_keep, f_sim = l / len(entry), l / len(new)
            if abs(f_keep - 0.25) <= 1 / len(entry):
                near.append(f"cache entry {idx}: kept fraction {f_keep:.4f} within one token of 0.25")
            if f_keep < 0.25:
                continue
            if 0 < abs(f_keep - f_keep_best) <= 1 / len(entry) or 0 < abs(f_sim - f_sim_best) <= 1 / len(new):
                near.append(f"cache entry {idx}: beats or loses to the slot by one token")
            if f_keep > f_keep_best and f_sim > f_sim_best:
                f_keep_best, f_sim_best, found = f_keep, f_sim, idx
        if found is None:
            return False
        self.slots[slot] = self.cache.pop(found)
        return True

    # --- one request ----------------------------------------------------------------------------

    def predict(self, new: list[Token]) -> Prediction:
        """What the next request reuses, leaving the state as it is."""
        clone = SlotSim(len(self.slots), self.similarity, self.limit, self.bpt)
        clone.slots = [list(s) for s in self.slots]
        clone.last_used = list(self.last_used)
        clone.cache = [list(c) for c in self.cache]
        clone.requests = self.requests
        return clone._select(new)

    def _select(self, new: list[Token]) -> Prediction:
        """get_available_slot, mutating this object."""
        if not new:
            raise ValueError("an empty request")
        near: list[str] = []
        best, f_sim_best = None, 0.0
        for i, held in enumerate(self.slots):
            if not held:
                continue
            f_sim = lcp(held, new) / len(new)
            if abs(f_sim - self.similarity) <= 1 / len(new):
                near.append(f"slot {i}: similarity {f_sim:.4f} within one token of {self.similarity}")
            if f_sim > f_sim_best and f_sim > self.similarity:
                f_sim_best, best = f_sim, i
        f_keep = None
        if best is not None:
            held = self.slots[best]
            f_keep = lcp(held, new) / len(held)
            if abs(f_keep - 0.5) <= 1 / len(held):
                near.append(f"slot {best}: kept fraction {f_keep:.4f} within one token of 0.5")
            update, by, f_sim = f_keep < 0.5, "similarity", f_sim_best
        else:
            best = min(range(len(self.slots)), key=lambda i: (self.last_used[i], i))
            update, by, f_sim = True, "lru", None
        saved, erased, evicted, restored = False, 0, 0, False
        if update:
            saved, erased, evicted = self._save(self.slots[best], near)
            restored = self._load(best, new, near)
        reuse = min(lcp(self.slots[best], new), len(new) - 1)
        return Prediction(reuse, best, by, f_sim, f_keep, update, saved, restored, erased, evicted, near)

    def commit(self, new: list[Token], fed_back: list[Token] = ()) -> int:
        """Send the request: select (as `predict` did), then hold the prompt — plus the generated tokens
        fed back as inputs of further steps, none when one token is generated — in the chosen slot,
        and save and clear every other idle slot. Returns the slot."""
        p = self._select(new)
        self.requests += 1
        self.slots[p.slot] = [*new, *fed_back]
        self.last_used[p.slot] = self.requests
        for i, held in enumerate(self.slots):
            if i != p.slot and held:
                self._save(held, [])
                self.slots[i] = []
        return p.slot

    def step(self, new: list[Token], fed_back: list[Token] = ()) -> Prediction:
        p = self.predict(new)
        self.commit(new, fed_back)
        return p
