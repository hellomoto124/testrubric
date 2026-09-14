"""Pure host-side scoring for V2 indicator judgments."""


def score(config: dict, judgments: list[dict]) -> dict:
    indicators = [item for group in config["groups"] for item in group["indicators"]]
    by_code = {item["indicator_code"]: item for item in judgments}
    codes = [item.get("code", item.get("indicator_code")) for item in indicators]
    known = [by_code[code]["ordinal_score"] for code in codes if code in by_code and by_code[code]["observation_state"] == "observed"]
    if not known:
        return {"score_state": "insufficient_evidence", "attained_level": None, "progress": None}
    progress = sum(known) / (4 * len(known))
    return {"score_state": "exact", "attained_level": max(1, min(6, round(1 + progress * 5))), "progress": progress}
