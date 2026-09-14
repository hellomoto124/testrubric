from decimal import ROUND_HALF_UP, Decimal


def _score(config, judgments, unknown):
    complete = 0
    for item in config:
        values = [unknown if value == "unknown" else Decimal(str(value)) for value in judgments.get(item["level"], [])]
        if not values or not all(value == 4 for value in values):
            progress = sum(values) / Decimal(len(values)) / 4 if values else Decimal(0)
            return complete, progress, Decimal(complete * 100) + progress * 100
        complete = item["level"]
    return 6, Decimal(0), Decimal(600)


def anchor_interp_v1(config, judgments, target=None):
    flat = [value for values in judgments.values() for value in values]
    if "conflict" in flat:
        return {"score_state": "needs_review", "attained_level": None, "raw_score": None, "display_score": None}
    if not [value for value in flat if value != "unknown"]:
        return {"score_state": "insufficient_evidence", "attained_level": None, "raw_score": None, "display_score": None}
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
    return {"score_state": "exact" if exact else "bounded", "attained_level": low_l or None, "next_level": None if low_l == 6 else low_l + 1, "progress": None if low_l == 6 else float(low_p), "raw_score": float(low) if exact else None, "display_score": int(low.quantize(Decimal(1), rounding=ROUND_HALF_UP)) if exact else None, "score_lower": None if exact else float(low), "score_upper": None if exact else float(high), "target_status": target_status, "target_gap": float(gap) if isinstance(gap, Decimal) else [float(x) for x in gap] if gap else None}
