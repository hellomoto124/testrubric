import pytest

from app.assessment_v2 import score


CONFIG = {"groups": [{"level": level, "weight": 1, "indicators": [{"database_id": level, "weight": 1}]} for level in range(1, 7)]}


def judgment(indicator_id, state="observed", value=4):
    return {"indicator_id": indicator_id, "observation_state": state, "ordinal_score": value if state == "observed" else None, "evidence_refs": [1], "fragment_locator": "0:1", "reason": "模拟测试", "support_context": "none"}


def test_host_uses_anchor_interpolation_for_exact_bounded_insufficient_and_conflict():
    assert score(CONFIG, [judgment(item) for item in range(1, 7)])["score_state"] == "exact"
    assert score(CONFIG, [judgment(1), judgment(2, "unknown")])["score_state"] == "bounded"
    assert score(CONFIG, [judgment(1, "unrelated")])["score_state"] == "insufficient_evidence"
    assert score(CONFIG, [judgment(1, "conflict")])["score_state"] == "needs_review"


@pytest.mark.parametrize("bad", [
    {"indicator_id": 1, "observation_state": "observed", "ordinal_score": 5, "evidence_refs": [], "fragment_locator": "x", "reason": "x", "support_context": "x"},
    {"indicator_id": 1, "observation_state": "unknown", "ordinal_score": 0, "evidence_refs": [], "fragment_locator": "x", "reason": "x", "support_context": "x"},
    {"indicator_id": 1, "observation_state": "observed", "ordinal_score": 1, "evidence_refs": [], "fragment_locator": "x", "reason": "x", "support_context": "x", "weights": 1},
])
def test_rejects_invalid_scores_and_unrelated_model_fields(bad):
    with pytest.raises(ValueError):
        score(CONFIG, [bad])
