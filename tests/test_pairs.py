"""The shared two-request evaluation: prediction from stored tokens, the render diff, the controls'
checks, the match."""
import pytest

from prefix_mortality.pairs import PREDICTION_KEYS, evaluate_pair, prediction, render_diff
from prefix_mortality.record import store_request


def test_prediction_follows_the_rule_and_corrects_an_identical_render_to_n_minus_1():
    assert prediction("prefix", 0.10, 0.002, [1, 2, 3, 4], [1, 2, 9, 4]) == \
        {"first_differing_token": 2, "predicted_reuse": 2, "near_threshold": False}
    assert prediction("threshold", 0.10, 0.002, list(range(1000)), list(range(99)) + [-1] * 901)["predicted_reuse"] == 0
    assert prediction("threshold", 0.10, 0.002, list(range(1000)), list(range(101)) + [-1] * 899)["predicted_reuse"] == 101
    assert prediction("threshold", 0.10, 0.002, list(range(1000)), list(range(101)) + [-1] * 899)["near_threshold"] is True
    assert prediction("prefix", 0.10, 0.002, [1, 2], [1, 2]) == {"first_differing_token": 2, "predicted_reuse": 1, "near_threshold": False}
    assert prediction("threshold", 0.10, 0.002, [1, 2], [1, 2])["predicted_reuse"] == 1
    assert prediction("prefix", 0.10, 0.002, [1, 2, 3], [1, 2])["predicted_reuse"] == 2, "a strict prefix is not a resend"


def test_render_diff():
    assert render_diff("abc", "abc") is None
    assert render_diff("abc", "abd") == 2
    assert render_diff("abc", "abcd") == 3
    assert render_diff("", "a") == 0


def _stored(tmp_path, body: str, rendered: str, ids: list[int]) -> str:
    return store_request(tmp_path, body.encode("utf-8"), rendered, [{"id": i, "piece": p} for i, p in zip(ids, rendered.split(" "))])


def _record(sha, nonce, cache_n, prompt_n, cached=None, **extra):
    return {"request_sha256": sha, "nonce": nonce,
            "observed": {"cache_n": cache_n, "prompt_n": prompt_n,
                         "usage_cached_tokens": cache_n if cached is None else cached}, **extra}


def test_evaluate_pair_matches_a_faithful_pair_and_reports_the_render_diff(tmp_path):
    # the rendered prompt is "run <nonce> a b c" with one token per word; h = 2 (the words up to the nonce)
    base = _stored(tmp_path, '{"x":1}', "run n1 a b c", [1, 2, 3, 4, 5])
    changed = _stored(tmp_path, '{"x":2}', "run n1 a X c", [1, 2, 3, 9, 5])
    p = prediction("prefix", 0.10, 0.002, [1, 2, 3, 4, 5], [1, 2, 3, 9, 5])
    out = evaluate_pair(_record(base, "n1", 0, 5), _record(changed, "n1", 3, 2, **p), tmp_path, "prefix", 0.10, 0.002)
    assert out["failures"] == [] and out["unmeasurable"] == [] and out["match"] is True
    assert out["render_diff"] == len("run n1 a ")
    assert out["base"]["n"] == 5 and out["base"]["h"] == 2 and out["changed"]["predicted_reuse"] == 3
    assert set(PREDICTION_KEYS) <= set(out["changed"])


def test_evaluate_pair_names_each_failed_control(tmp_path):
    base = _stored(tmp_path, '{"x":1}', "run n1 a b c", [1, 2, 3, 4, 5])
    changed = _stored(tmp_path, '{"x":2}', "run n2 a X c", [1, 7, 3, 9, 5])      # another nonce: d = 1
    p = prediction("prefix", 0.10, 0.002, [1, 2, 3, 4, 5], [1, 7, 3, 9, 5])
    assert p["predicted_reuse"] == 1
    bad = evaluate_pair(_record(base, "n1", 4, 1), _record(changed, "n2", 1, 3, cached=2, **{**p, "predicted_reuse": 2}),
                        tmp_path, "prefix", 0.10, 0.002)
    assert set(bad["failures"]) == {"same_nonce", "prediction_as_recorded", "base_reuses_at_most_header",
                                    "changed_counts_add_up", "changed_fields_agree"}
    assert bad["match"] is True, "the match is still computed against the recomputed prediction"


def test_evaluate_pair_refuses_a_record_whose_nonce_is_not_in_its_own_render(tmp_path):
    base = _stored(tmp_path, '{"x":1}', "run n1 a b c", [1, 2, 3, 4, 5])
    changed = _stored(tmp_path, '{"x":2}', "run n1 a X c", [1, 2, 3, 9, 5])
    with pytest.raises(ValueError, match="not isolated"):
        evaluate_pair(_record(base, "n1", 0, 5), _record(changed, "n2", 3, 2), tmp_path, "prefix", 0.10, 0.002)


def test_evaluate_pair_is_not_measurable_without_a_field_and_does_not_judge(tmp_path):
    base = _stored(tmp_path, '{"x":1}', "run n1 a b c", [1, 2, 3, 4, 5])
    changed = _stored(tmp_path, '{"x":2}', "run n1 a X c", [1, 2, 3, 9, 5])
    rec = _record(changed, "n1", 3, 2)
    rec["observed"]["cache_n"] = None
    out = evaluate_pair(_record(base, "n1", 0, 5), rec, tmp_path, "prefix", 0.10, 0.002)
    assert out["unmeasurable"] == ["changed: the server reported no cache_n"] and out["match"] is None and out["failures"] == []


def test_evaluate_pair_flags_an_identical_render_as_no_diff_and_predicts_n_minus_1(tmp_path):
    base = _stored(tmp_path, '{"x":1}', "run n1 a b c", [1, 2, 3, 4, 5])
    changed = _stored(tmp_path, '{"x":1,"y":2}', "run n1 a b c", [1, 2, 3, 4, 5])
    p = prediction("prefix", 0.10, 0.002, [1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
    assert p["predicted_reuse"] == 4
    out = evaluate_pair(_record(base, "n1", 0, 5), _record(changed, "n1", 4, 1, **p), tmp_path, "prefix", 0.10, 0.002)
    assert out["render_diff"] is None
    assert out["changed"]["predicted_reuse"] == 4, "an identical render is a resend: the server reuses n - 1"
    assert out["match"] is True
