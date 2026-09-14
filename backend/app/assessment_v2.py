"""Strict V2 judgment adapter around the canonical host scorer."""

from .scoring import anchor_interp_v1


FIELDS = {"indicator_id", "observation_state", "ordinal_score", "evidence_refs", "fragment_locator", "reason", "support_context"}
STATES = {"observed", "unknown", "unrelated", "conflict"}


def score(config: dict, judgments: list[dict], target_level: int | None = None) -> dict:
    normalized = {}
    for item in judgments:
        if set(item) != FIELDS or type(item["indicator_id"]) is not int or item["observation_state"] not in STATES:
            raise ValueError("invalid indicator judgment")
        observed = item["observation_state"] == "observed"
        if (observed and (type(item["ordinal_score"]) is not int or item["ordinal_score"] not in range(5))) or (not observed and item["ordinal_score"] is not None) or item["indicator_id"] in normalized:
            raise ValueError("invalid indicator judgment")
        normalized[item["indicator_id"]] = {"state": item["observation_state"], "score": item["ordinal_score"]}
    levels = [{"level": group["level"], "groups": [{"weight": group["weight"], "indicators": [{"id": indicator.get("database_id", indicator.get("id")), "weight": indicator["weight"]} for indicator in group["indicators"]]}]} for group in config["groups"]]
    return anchor_interp_v1(levels, normalized, target_level)
