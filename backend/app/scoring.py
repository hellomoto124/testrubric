from decimal import Decimal, ROUND_HALF_UP


def anchor_interp_v1(config, judgments, target=None):
    """Deterministic six-level anchor interpolation; inputs are 0..4 or states."""
    if any(value == "conflict" for values in judgments.values() for value in values):
        return {"status": "needs_review", "attained_level": None, "score": None}
    known = [value for values in judgments.values() for value in values if value != "unknown"]
    if not known:
        return {"status": "insufficient", "attained_level": None, "score": None}
    complete = 0
    progress = Decimal("0")
    for group in config:
        level = group["level"]
        values = [Decimal(str(value)) for value in judgments.get(level, []) if value != "unknown"]
        if not values:
            break
        if all(value == 4 for value in values):
            complete = level
            continue
        progress = sum(values) / Decimal(len(values)) / Decimal(4)
        break
    score = Decimal(600) if complete == 6 else Decimal(complete * 100) + progress * Decimal(100)
    attained = complete or None
    display = score.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    target_status = None if target is None else ("met_target" if complete >= target else "below_target")
    return {"status": "scored", "attained_level": attained, "score": float(display), "target_status": target_status, "target_gap": None if target is None else max(target - complete, 0)}
