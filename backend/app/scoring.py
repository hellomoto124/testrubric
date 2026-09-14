from decimal import ROUND_HALF_UP, Decimal


def _level_values(level_config, judgments, unknown):
    raw = judgments.get(level_config["level"], [])
    groups = level_config.get("groups")
    if not groups:
        return [(Decimal(1) / len(level_config["indicators"]), unknown if value == "unknown" else Decimal(str(value))) for value in raw]
    values = []
    for group_index, group in enumerate(groups):
        items = raw.get(group_index, []) if isinstance(raw, dict) else raw
        group_weight = Decimal(str(group.get("weight", 1 / len(groups))))
        weights = [Decimal(str(item.get("weight", 1 / len(group["indicators"])))) for item in group["indicators"]]
        if not items or len(items) != len(weights) or sum(weights) != 1:
            raise ValueError("invalid indicator weights or judgments")
        values.extend((group_weight * weight, unknown if value == "unknown" else Decimal(str(value))) for weight, value in zip(weights, items))
    if sum(weight for weight, _value in values) != 1:
        raise ValueError("invalid group weights")
    return values


def _score(config, judgments, unknown):
    complete = 0
    for item in config:
        values = _level_values(item, judgments, unknown)
        if not values or not all(value == 4 for _weight, value in values):
            progress = sum(weight * value for weight, value in values) / 4 if values else Decimal(0)
            return complete, progress, Decimal(complete * 100) + progress * 100
        complete = item["level"]
    return 6, Decimal(0), Decimal(600)


def anchor_interp_v1(config, judgments, target=None):
    flat = [value for values in judgments.values() for value in (values.values() if isinstance(values, dict) else [values]) for value in (value if isinstance(value, list) else [value])]
    if any(type(value) is not int and value not in {"unknown", "conflict"} or type(value) is int and not 0 <= value <= 4 for value in flat):
        raise ValueError("invalid judgment")
    if "conflict" in flat:
        return {"score_state": "needs_review", "attained_level": None, "score_raw": None, "score_display": None, "scoring_version": "anchor_interp_v1"}
    if not [value for value in flat if value != "unknown"]:
        return {"score_state": "insufficient_evidence", "attained_level": None, "score_raw": None, "score_display": None, "scoring_version": "anchor_interp_v1"}
    low_l, low_p, low = _score(config, judgments, Decimal(0))
    _high_l, _high_p, high = _score(config, judgments, Decimal(4))
    exact = "unknown" not in flat
    target_score = Decimal(target * 100) if target else None
    if target_score is None:
        target_status, gap = "not_configured", None
    elif exact:
        target_status = "below_target" if low < target_score else "meets_target" if low == target_score else "above_target"
        gap = low - target_score
    elif high < target_score:
        target_status, gap = "below_target", (low - target_score, high - target_score)
    elif low > target_score:
        target_status, gap = "above_target", (low - target_score, high - target_score)
    else:
        target_status, gap = "uncertain", (low - target_score, high - target_score)
    return {"score_state": "exact" if exact else "bounded", "attained_level": low_l or None, "next_level": None if low_l == 6 else low_l + 1, "next_level_progress": None if low_l == 6 else float(low_p), "score_raw": float(low) if exact else None, "score_display": int(low.quantize(Decimal(1), rounding=ROUND_HALF_UP)) if exact else None, "score_lower": None if exact else float(low), "score_upper": None if exact else float(high), "target_level": target, "target_score": float(target_score) if target_score else None, "target_gap": float(gap) if isinstance(gap, Decimal) else None, "target_gap_lower": float(gap[0]) if isinstance(gap, tuple) else None, "target_gap_upper": float(gap[1]) if isinstance(gap, tuple) else None, "target_status": target_status, "scoring_version": "anchor_interp_v1"}
