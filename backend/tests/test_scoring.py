import pytest
from app.scoring import anchor_interp_v1


def config(weights=(1, 1, 1)):
    return [
        {
            "level": level,
            "groups": [
                {
                    "weight": 1,
                    "indicators": [
                        {"id": f"L{level}I{i}", "weight": weight / sum(weights)}
                        for i, weight in enumerate(weights, 1)
                    ],
                }
            ],
        }
        for level in range(1, 7)
    ]


def judgments(values, weights=(1, 1, 1)):
    return {
        f"L{level}I{i}": {
            "state": "observed",
            "score": values.get(level, [0, 0, 0])[i - 1],
        }
        for level in range(1, 7)
        for i in range(1, 4)
    }


def complete_to(level, next_values=(0, 0, 0)):
    return {
        **{item: [4, 4, 4] for item in range(1, level + 1)},
        level + 1: list(next_values),
    }


def test_a01_342():
    assert (
        anchor_interp_v1(config(), judgments(complete_to(3, (3, 2, 0))), 3)[
            "score_display"
        ]
        == 342
    )


def test_a02_358():
    assert (
        anchor_interp_v1(config(), judgments(complete_to(3, (3, 2, 2))), 3)[
            "score_display"
        ]
        == 358
    )


def test_a03_425():
    assert (
        anchor_interp_v1(config(), judgments(complete_to(4, (2, 1, 0))), 3)["score_raw"]
        == 425
    )


def test_a04_125():
    assert (
        anchor_interp_v1(config(), judgments(complete_to(1, (2, 1, 0))), 4)[
            "target_gap"
        ]
        == -275
    )


def test_a05_292():
    assert (
        anchor_interp_v1(config(), judgments(complete_to(2, (4, 4, 3))), 3)[
            "score_display"
        ]
        == 292
    )


def test_a06_600():
    assert (
        anchor_interp_v1(
            config(), judgments({level: [4, 4, 4] for level in range(1, 7)}), 4
        )["score_raw"]
        == 600
    )


def test_a07_bounded():
    data = judgments(complete_to(3, (3, 2, 0)))
    data["L4I3"] = {"state": "unknown"}
    result = anchor_interp_v1(config(), data, 4)
    assert (result["score_lower"], result["score_upper"]) == (341.6666666666667, 375.0)


def test_a08_all_unknown():
    assert (
        anchor_interp_v1(config(), {"L1I1": {"state": "unknown"}})["score_state"]
        == "insufficient_evidence"
    )


def test_a09_conflict():
    assert (
        anchor_interp_v1(config(), {"L1I1": {"state": "conflict"}})["score_state"]
        == "needs_review"
    )


def test_a10_level_one_null():
    assert (
        anchor_interp_v1(config(), judgments({1: [3, 0, 0]}))["attained_level"] is None
    )


def test_a11_full_progress_promotes():
    assert (
        anchor_interp_v1(config(), judgments(complete_to(3, (4, 4, 4))))[
            "attained_level"
        ]
        == 4
    )


def test_a12_weights():
    assert (
        anchor_interp_v1(config((2, 1, 1)), judgments(complete_to(3, (4, 0, 0))))[
            "score_raw"
        ]
        == 350
    )


def test_a13_invalid_weights():
    with pytest.raises(ValueError):
        anchor_interp_v1(
            [
                {
                    "level": 1,
                    "groups": [
                        {"weight": 0.5, "indicators": [{"id": "x", "weight": 1}]}
                    ],
                }
            ],
            {"x": {"state": "observed", "score": 1}},
        )


def test_a14_invalid_score():
    with pytest.raises(ValueError):
        anchor_interp_v1(config(), {"L1I1": {"state": "observed", "score": 5}})


def test_a15_version():
    assert (
        anchor_interp_v1(config(), judgments({1: [1, 0, 0]}))["scoring_version"]
        == "anchor_interp_v1"
    )


def test_a16_target_changes_not_score():
    data = judgments(complete_to(3, (0.5, 0, 0)))
    assert (
        anchor_interp_v1(config(), data, 3)["score_raw"]
        == anchor_interp_v1(config(), data, 4)["score_raw"]
    )


def test_a17_deterministic():
    data = judgments(complete_to(2, (0.5, 0, 0)))
    assert anchor_interp_v1(config(), data) == anchor_interp_v1(config(), data)
