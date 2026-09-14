"""Strict V2 judgment adapter around the canonical host scorer."""

from .scoring import anchor_interp_v1


FIELDS = {"indicator_id", "observation_state", "ordinal_score", "evidence_refs", "fragment_locator", "reason", "support_context"}
STATES = {"observed", "unknown", "unrelated", "conflict"}


def score(
    config: dict,
    judgments: list[dict],
    target_level: int | None = None,
    allowed_evidence_refs: set[int] | None = None,
) -> dict:
    configured_ids = {
        indicator.get("database_id", indicator.get("id"))
        for group in config["groups"]
        for indicator in group["indicators"]
    }
    normalized = {}
    for item in judgments:
        if set(item) != FIELDS or type(item["indicator_id"]) is not int or item["observation_state"] not in STATES:
            raise ValueError("invalid indicator judgment")
        observed = item["observation_state"] == "observed"
        refs = item["evidence_refs"]
        if (
            observed
            and (
                type(item["ordinal_score"]) is not int
                or item["ordinal_score"] not in range(5)
                or not refs
            )
            or not observed
            and item["ordinal_score"] is not None
            or not isinstance(refs, list)
            or any(type(ref) is not int for ref in refs)
            or len(refs) != len(set(refs))
            or allowed_evidence_refs is not None
            and not set(refs) <= allowed_evidence_refs
            or item["indicator_id"] in normalized
        ):
            raise ValueError("invalid indicator judgment")
        normalized[item["indicator_id"]] = {"state": item["observation_state"], "score": item["ordinal_score"]}
    if set(normalized) != configured_ids:
        raise ValueError("judgments must contain exactly the configured indicators")
    levels = [{"level": group["level"], "groups": [{"weight": group["weight"], "indicators": [{"id": indicator.get("database_id", indicator.get("id")), "weight": indicator["weight"]} for indicator in group["indicators"]]}]} for group in config["groups"]]
    return anchor_interp_v1(levels, normalized, target_level)
