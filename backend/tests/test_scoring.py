from app.scoring import anchor_interp_v1


def test_anchor_interp_reports_complete_level_and_next_level_progress():
    config = [{"level": level, "indicators": ["a", "b"]} for level in range(1, 7)]

    result = anchor_interp_v1(config, {1: [4, 4], 2: [4, 4], 3: [4, 4], 4: [2, 1]}, target=4)

    assert result["score"] == 337.5
    assert result["attained_level"] == 3
    assert result["target_status"] == "below_target"


def test_anchor_interp_handles_unknown_conflict_and_level_six():
    config = [{"level": level, "indicators": ["a"]} for level in range(1, 7)]

    assert anchor_interp_v1(config, {1: ["unknown"]})["status"] == "insufficient"
    assert anchor_interp_v1(config, {1: ["conflict"]})["status"] == "needs_review"
    assert anchor_interp_v1(config, {level: [4] for level in range(1, 7)})["score"] == 600
