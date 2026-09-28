"""Adapted from linear-ceiling tests/test_lint_scope.py: same cases, re-anchored on this repo's sentence."""
import io

import pytest

from prefix_mortality.lint_scope import SCOPE_SENTENCE, _overlap_score, _ascii_safe, check_paraphrase, check_readme


def test_scope_sentence_is_the_registered_text():
    assert SCOPE_SENTENCE == ("This repository measures how long a cached prompt prefix survives and which "
                              "registered change ends it, read from provider-reported usage and "
                              "serving-engine cache counters; it does not measure output quality or serving "
                              "latency.")


def test_scope_sentence_is_the_one_the_ledger_founded():
    from prefix_mortality import REPO_ROOT
    from prefix_mortality.lint_scope import _normalize
    ledger = (REPO_ROOT / "ledger" / "ledger.md").read_text(encoding="utf-8")
    assert SCOPE_SENTENCE in _normalize(ledger)


def test_readme_needs_exactly_one():
    assert check_readme("no sentence here") == ["README.md: scope sentence appears 0 times, expected exactly 1"]
    assert check_readme(SCOPE_SENTENCE + "\n\n" + SCOPE_SENTENCE) == \
        ["README.md: scope sentence appears 2 times, expected exactly 1"]
    assert check_readme("x\n" + SCOPE_SENTENCE + "\ny") == []


def test_wrapped_verbatim_sentence_counts_as_one():
    wrapped = ("> This repository measures how long a cached prompt prefix survives and which registered\n"
               "> change ends it, read from provider-reported usage and serving-engine cache counters; it\n"
               "> does not measure output quality or serving latency.")
    assert check_readme(wrapped) == []


PARAPHRASE = ("This repository measures how long a cached prefix survives and which change ends it, read "
              "from provider usage and engine cache counters; serving latency is not measured.")
NEAR_MISS = ("The two controls send one prompt twice and halt before any table is written when the "
             "engine reports nothing reused.")


def test_anchor_scores_sit_on_either_side_of_the_threshold():
    # The threshold (0.45) was calibrated in linear-ceiling on its own sentence; these two anchors
    # re-establish the margin on this repo's sentence. If either drifts across, recalibrate, don't tune.
    assert _overlap_score(PARAPHRASE) >= 0.60
    assert _overlap_score(NEAR_MISS) <= 0.30


def test_paraphrase_is_flagged():
    result = check_paraphrase(PARAPHRASE, "docs/x.md")
    assert len(result) == 1 and "closely paraphrases the scope sentence" in result[0] and PARAPHRASE in result[0]
    assert check_paraphrase(SCOPE_SENTENCE, "docs/x.md") == []


def test_paraphrase_joined_by_arrow_is_also_flagged():
    text = PARAPHRASE.replace("; serving", " → serving")
    result = check_paraphrase(text, "docs/x.md")
    assert len(result) == 1 and text in result[0]


def test_near_miss_that_shares_keywords_stays_unflagged_on_overlap():
    assert check_paraphrase(NEAR_MISS, "ledger/ledger.md") == []


def test_flagged_nonascii_sentence_is_reported_without_raising():
    text = PARAPHRASE.replace("This repository", "This repository ρ")
    problems = check_paraphrase(text, "docs/rho.md")
    assert len(problems) == 1 and "ρ" in problems[0]
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    with pytest.raises(UnicodeEncodeError):
        print("SCOPE:", problems[0], file=stream)
    print("SCOPE:", _ascii_safe(problems[0]), file=stream)
    stream.flush()
    buf = stream.buffer.getvalue().decode("cp1252")
    assert "SCOPE:" in buf and "latency" in buf and "\\u03c1" in buf


def test_repo_passes():
    from prefix_mortality.lint_scope import main
    assert main() == 0
