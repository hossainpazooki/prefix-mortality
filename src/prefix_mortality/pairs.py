"""Two requests under one nonce, the second changed from the first: the evaluation M2 and M3 share.

From the stored tokens of both requests, d is the number of leading tokens their rendered prompts
have in common and n the changed prompt's length; the hypothesis's rule (prefix or threshold, as in
summarize_m1) predicts the changed request's reuse from d and n. One correction: when the two renders
are identical, d equals n and the changed request is a byte-identical resend of the prompt, which the
engine reuses to n - 1 (ledger 0003); the prediction is then n - 1.

The base request is held to the controls' rule for a write (it reuses at most h, the tokens that
start before the end of the nonce); both requests' counts must add up and their two reuse fields
agree. A field the server did not report makes the pair NOT MEASURABLE, never 0.
"""
from pathlib import Path

from prefix_mortality.record import load_request
from prefix_mortality.summarize import FIELDS, header_tokens
from prefix_mortality.summarize_m1 import common_prefix, near_threshold, predict

PREDICTION_KEYS = ("first_differing_token", "predicted_reuse", "near_threshold")


def prediction(rule: str, threshold: float, margin: float, base_ids: list[int], changed_ids: list[int]) -> dict:
    """The rule applied to the two token lists; identical renders are corrected to n - 1 here."""
    d, n = common_prefix(base_ids, changed_ids), len(changed_ids)
    reuse = predict(rule, d, n, threshold)
    if d == n and len(base_ids) == n and n > 0:
        reuse = n - 1
    return {"first_differing_token": d, "predicted_reuse": reuse,
            "near_threshold": near_threshold(rule, d, n, threshold, margin)}


def render_diff(a: str, b: str) -> int | None:
    """Index of the first differing character, or None when the two texts are equal."""
    if a == b:
        return None
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _ids(stored: dict) -> list[int]:
    return [t["id"] for t in stored["tokens"]]


def _row(rec: dict, stored: dict) -> dict:
    o = rec["observed"]
    return {"request_sha256": rec["request_sha256"], "n": len(stored["tokens"]),
            "h": header_tokens(stored["tokens"], rec["nonce"]), **{f: o.get(f) for f in FIELDS}}


def evaluate_pair(base: dict, changed: dict, requests_dir: Path, rule: str, threshold: float, margin: float) -> dict:
    """One pair from its two records. `failures` are failed controls; `match` is the result."""
    sb, sc = load_request(requests_dir, base["request_sha256"]), load_request(requests_dir, changed["request_sha256"])
    rows = {"base": _row(base, sb), "changed": _row(changed, sc)}
    out = {"failures": [], "unmeasurable": [], "match": None, "render_diff": render_diff(sb["rendered"], sc["rendered"]),
           **rows}
    for role in ("base", "changed"):
        missing = [f for f in FIELDS if rows[role][f] is None]
        if missing:
            out["unmeasurable"].append(f"{role}: the server reported no {', '.join(missing)}")
    p = prediction(rule, threshold, margin, _ids(sb), _ids(sc))
    out["changed"].update(p)
    if out["unmeasurable"]:
        return out
    b, c = rows["base"], rows["changed"]
    checks = {"same_nonce": base["nonce"] == changed["nonce"],
              "prediction_as_recorded": {k: changed.get(k) for k in PREDICTION_KEYS} == p,
              "base_reuses_at_most_header": b["cache_n"] <= b["h"],
              "base_counts_add_up": b["cache_n"] + b["prompt_n"] == b["n"],
              "base_fields_agree": b["usage_cached_tokens"] == b["cache_n"],
              "changed_counts_add_up": c["cache_n"] + c["prompt_n"] == c["n"],
              "changed_fields_agree": c["usage_cached_tokens"] == c["cache_n"]}
    out["failures"] = [k for k, ok in checks.items() if not ok]
    out["match"] = c["cache_n"] == c["predicted_reuse"]
    return out
