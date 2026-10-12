"""The slot and prompt-cache policy as the source states it: an identical resend reuses n - 1; a
strict extension reuses the previous prompt and one more when the sampled token matches; two
conversations sharing a head block each other's restore when the held prompt is under twice the head;
a head over half lost is saved but not restored later; the LRU path restores from the cache and a
small cache loses the state; decisions within one token are flagged; the cache-reuse walk shifts a
trimmed tail and finds nothing past an inserted summary; and the stand-in agrees with the simulator
on random sequences."""
import random

import pytest

from prefix_mortality.slotsim import SlotSim, cache_reuse_walk, lcp, tokens
from tests.fake_llamacpp import Engine


def T(ids):
    return tokens(list(ids), [str(i) for i in ids])


HEAD = T(range(100))
A, B = HEAD + T(range(1000, 1060)), HEAD + T(range(2000, 2060))


def test_identical_resend_into_a_held_slot_reuses_n_minus_one():
    sim = SlotSim(slots=1)
    assert sim.step(A).reuse == 0
    p = sim.step(A)
    assert p.reuse == 159 and p.by == "similarity" and not p.cache_searched


def test_a_strict_extension_reuses_the_previous_prompt_and_a_fed_back_token_only_when_one_was_held():
    sim = SlotSim(slots=1)
    sim.step(A)                                               # one token generated: nothing fed back
    more = T(range(3000, 3020))
    assert sim.predict(A + more).reuse == 160
    sim2 = SlotSim(slots=1)
    sim2.step(A, [(None, "3000")])                            # a generated token fed back, known by its text
    assert sim2.predict(A + more).reuse == 161
    sim3 = SlotSim(slots=1)
    sim3.step(A, [(None, "other")])
    assert sim3.predict(A + more).reuse == 160


def test_a_shared_head_under_half_of_the_held_prompt_blocks_the_cache():
    sim = SlotSim(slots=4, cache_limit_bytes=10**9)
    sim.step(A)
    p = sim.step(B)                                           # f_sim 100/160, f_keep 100/160 >= 0.5
    assert (p.reuse, p.by, p.cache_searched, p.saved) == (100, "similarity", False, False)
    assert sim.cache == []                                    # A's state was never saved
    p = sim.step(A + T(range(3000, 3020)))                    # A's own continuation finds B in the slot
    assert (p.reuse, p.cache_searched) == (100, False)


def test_a_head_over_half_lost_is_saved_and_the_slot_keeps_its_prompt_but_the_state_is_never_restored():
    long_a = HEAD + T(range(1000, 1200))                      # 300 held
    sim = SlotSim(slots=4, cache_limit_bytes=10**9)
    sim.step(long_a)
    p = sim.step(B)                                           # f_keep 100/300 < 0.5: save, search
    assert (p.reuse, p.cache_searched, p.saved, p.restored) == (100, True, True, False)
    assert len(sim.cache) == 1 and len(sim.cache[0]) == 300
    p = sim.step(long_a + T(range(3000, 3020)))               # slot holds B: f_keep 100/160 >= 0.5, no search
    assert (p.reuse, p.cache_searched, p.restored) == (100, False, False)
    assert len(sim.cache) == 1                                # the cached state sits unused


@pytest.mark.parametrize("states_fit,expected,evicted", [(2, 99, 0), (1, 0, 1)])
def test_the_lru_path_restores_from_the_cache_while_it_fits(states_fit, expected, evicted):
    X, F1, F2 = T(range(100)), T(range(5000, 5100)), T(range(6000, 6100))
    sim = SlotSim(slots=4, cache_limit_bytes=100 * states_fit, bytes_per_token=1)
    for req in (X, F1, F2):
        assert sim.step(req).reuse == 0
    p = sim.predict(X)
    assert (p.reuse, p.by, p.cache_searched) == (expected, "lru", True)
    assert p.restored == (expected == 99)
    assert sum(1 for _ in sim.cache) == states_fit
    # the eviction happened when F1 was saved at F2's launch
    sim2 = SlotSim(slots=4, cache_limit_bytes=100 * states_fit, bytes_per_token=1)
    sim2.step(X); sim2.step(F1)
    assert len(sim2.cache) == 1
    sim2.step(F2)
    assert len(sim2.cache) == states_fit


def test_saving_skips_a_prompt_already_cached_and_erases_the_prompts_it_extends():
    sim = SlotSim(slots=4, cache_limit_bytes=10**9)
    short, long_ = T(range(50)), T(range(50)) + T(range(50, 120))
    sim.cache = [list(long_)]
    assert sim._save(list(short), []) == (False, 0, 0)        # a prefix of a cached prompt: already there
    assert sim._save(list(long_), []) == (False, 0, 0)        # itself
    sim.cache = [list(short), T(range(900, 950))]
    saved, erased, evicted = sim._save(list(long_), [])       # the short one is a prefix of it: obsolete
    assert (saved, erased, evicted) == (True, 1, 0) and [len(c) for c in sim.cache] == [50, 120]
    # a strict extension of a held conversation therefore keeps one state per conversation in the cache
    sim = SlotSim(slots=4, cache_limit_bytes=10**9)
    for n in (60, 90, 120):
        sim._save(T(range(n)), [])
    assert [len(c) for c in sim.cache] == [120]


def test_decisions_within_one_token_are_flagged():
    sim = SlotSim(slots=4, cache_limit_bytes=10**9)
    held = T(range(10)) + T(range(500, 590))                  # 100 tokens
    sim.step(held)
    new = T(range(10)) + T(range(700, 790))                   # shares exactly 10 of 100: f_sim 0.10, not above
    p = sim.predict(new)
    assert p.by == "lru" and any("within one token of 0.1" in x for x in p.near)
    assert SlotSim(slots=1).predict(T(range(5))).near == []


def test_the_walk_shifts_a_trimmed_tail_and_finds_nothing_past_an_inserted_summary():
    X, E, L, S = T(range(10)), T(range(100, 150)), T(range(1000, 1300)), T(range(7000, 7005))
    held = X + E + L
    assert cache_reuse_walk(held, X + L, 256) == (310, [(10, 60, 300)])
    assert cache_reuse_walk(held, X + S + L, 256) == (10, [])
    assert cache_reuse_walk(held, X + L, 301) == (10, [])
    broken = X + L[:150] + T([9]) + L[151:]                   # one differing token splits the run
    assert cache_reuse_walk(held, broken, 256) == (10, [])
    # the walk never skips a token of the NEW prompt: the differing token blocks everything after it
    assert cache_reuse_walk(held, broken, 100) == (160, [(10, 60, 150)])


def test_lcp_matches_a_token_without_an_id_by_its_text_only():
    assert lcp([(1, "a"), (None, "b")], [(1, "a"), (7, "b"), (8, "c")]) == 2
    assert lcp([(1, "a"), (None, "")], [(1, "a"), (7, "")]) == 1          # an empty text matches nothing


def test_the_stand_in_agrees_with_the_simulator_on_random_sequences():
    """Two readings of the same source lines: the stand-in's slot choice and cache, and the simulator's."""
    rng = random.Random(7)
    heads = [list(range(h * 100, h * 100 + 40)) for h in range(3)]
    for _ in range(150):
        slots = rng.choice([1, 4])
        limit = rng.choice([None, 60, 150, 10**6])
        e = Engine(slots=slots, cache_limit_bytes=limit, bytes_per_token=1, n_ctx=100000)
        sim = SlotSim(slots=slots, cache_limit_bytes=limit, bytes_per_token=1)
        convs = [list(rng.choice(heads)) for _ in range(3)]
        for step in range(8):
            c = rng.randrange(3)
            convs[c] = convs[c] + [rng.randrange(10**6) for _ in range(rng.randrange(1, 30))]
            ids = list(convs[c])
            got = e._serve_ids(ids)
            want = sim.step(T(ids))
            assert got == want.reuse, (slots, limit, step, got, want)
