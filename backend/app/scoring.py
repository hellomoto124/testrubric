from decimal import ROUND_HALF_UP, Decimal


def _items(level):
    if level["level"] not in range(1, 7):
        raise ValueError("invalid level")
    groups = level["groups"]
    if (
        not groups
        or any(Decimal(str(group["weight"])) <= 0 for group in groups)
        or abs(sum(Decimal(str(group["weight"])) for group in groups) - 1)
        > Decimal("0.000001")
    ):
        raise ValueError("invalid group weights")
    result = []
    for group in groups:
        indicators = group["indicators"]
        if (
            not indicators
            or len({item["id"] for item in indicators}) != len(indicators)
            or any(Decimal(str(item["weight"])) <= 0 for item in indicators)
            or abs(sum(Decimal(str(item["weight"])) for item in indicators) - 1)
            > Decimal("0.000001")
        ):
            raise ValueError("invalid indicator weights")
        result.extend(
            (item["id"], Decimal(str(group["weight"])) * Decimal(str(item["weight"])))
            for item in indicators
        )
    return result


def _score(config, judgments, unknown):
    complete = 0
    for level in config:
        values = []
        for indicator_id, weight in _items(level):
            judgment = judgments.get(indicator_id, {"state": "unknown"})
            state = judgment["state"]
            value = unknown if state == "unknown" else Decimal(str(judgment["score"]))
            if (
                state not in {"observed", "unknown", "unrelated"}
                or value < 0
                or value > 4
            ):
                raise ValueError("invalid judgment")
            values.append((weight, value))
        if not all(value == 4 for _weight, value in values):
            progress = sum(weight * value for weight, value in values) / 4
            return complete, progress, Decimal(complete * 100) + progress * 100
        complete = level["level"]
    return 6, Decimal(0), Decimal(600)


def anchor_interp_v1(config, judgments, target_level=None):
    if (
        [level["level"] for level in config] != [1, 2, 3, 4, 5, 6]
        or target_level is not None
        and (type(target_level) is not int or target_level not in range(1, 7))
    ):
        raise ValueError("invalid config or target")
    configured_ids = [
        indicator_id for level in config for indicator_id, _weight in _items(level)
    ]
    states = [
        judgments.get(indicator_id, {"state": "unknown"}).get("state")
        for indicator_id in configured_ids
    ]
    base = {
        "next_level": None,
        "next_level_progress": None,
        "score_raw": None,
        "score_display": None,
        "score_lower": None,
        "score_upper": None,
        "target_level": target_level,
        "target_score": target_level * 100 if target_level else None,
        "target_gap": None,
        "target_gap_lower": None,
        "target_gap_upper": None,
        "scoring_version": "anchor_interp_v1",
    }
    if "conflict" in states:
        return base | {
            "score_state": "needs_review",
            "attained_level": None,
            "target_status": "needs_review",
        }
    if not any(state == "observed" for state in states):
        return base | {
            "score_state": "insufficient_evidence",
            "attained_level": None,
            "target_status": "insufficient_evidence",
        }
    low_l, low_p, low = _score(config, judgments, Decimal(0))
    _high_l, _high_p, high = _score(config, judgments, Decimal(4))
    bounded = "unknown" in states
    target = Decimal(target_level * 100) if target_level else None
    if target is None:
        target_status, gap = "not_configured", None
    elif not bounded:
        target_status = (
            "below_target"
            if low < target
            else "meets_target"
            if low == target
            else "above_target"
        )
        gap = low - target
    elif high < target:
        target_status, gap = "below_target", (low - target, high - target)
    elif low > target:
        target_status, gap = "above_target", (low - target, high - target)
    else:
        target_status, gap = "uncertain", (low - target, high - target)
    return base | {
        "score_state": "bounded" if bounded else "exact",
        "attained_level": low_l or None,
        "next_level": None if low_l == 6 else low_l + 1,
        "next_level_progress": None if low_l == 6 else float(low_p),
        "score_raw": None if bounded else float(low),
        "score_display": None
        if bounded
        else int(low.quantize(Decimal(1), rounding=ROUND_HALF_UP)),
        "score_lower": float(low) if bounded else None,
        "score_upper": float(high) if bounded else None,
        "target_status": target_status,
        "target_gap": float(gap) if isinstance(gap, Decimal) else None,
        "target_gap_lower": float(gap[0]) if isinstance(gap, tuple) else None,
        "target_gap_upper": float(gap[1]) if isinstance(gap, tuple) else None,
    }
