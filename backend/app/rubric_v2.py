import sqlite3

from .database import connect


class V2NotFound(Exception):
    pass


class V2Conflict(Exception):
    pass


class V2Invalid(Exception):
    pass


def _current_rubric_id(connection):
    row = connection.execute(
        "SELECT id FROM rubric_versions_v2 WHERE code = 'kai_feng_yuyang_260910'"
    ).fetchone()
    if not row:
        raise V2NotFound("rubric not found")
    return row[0]


def _config_detail(connection, config_id):
    row = connection.execute(
        """SELECT id, rubric_id, skill_code, code, version, parent_config_id,
        status, calibration_status, is_simulated_test_data
        FROM scoring_configs_v2 WHERE id = ?""",
        (config_id,),
    ).fetchone()
    if not row:
        raise V2NotFound("config not found")
    config = dict(
        zip(
            (
                "id",
                "rubric_id",
                "skill_code",
                "code",
                "version",
                "parent_config_id",
                "status",
                "calibration_status",
                "is_simulated_test_data",
            ),
            row,
        )
    )
    config["is_simulated_test_data"] = bool(config["is_simulated_test_data"])
    groups = []
    for group_id, level, code, weight in connection.execute(
        "SELECT id, level, code, weight FROM indicator_groups_v2 WHERE config_id = ? ORDER BY level, id",
        (config_id,),
    ):
        indicators = []
        for indicator_id, indicator_code, source_text, indicator_weight in connection.execute(
            "SELECT id, code, source_text, weight FROM indicators_v2 WHERE group_id = ? ORDER BY id",
            (group_id,),
        ):
            anchors = [
                {"score": score, "text": text}
                for score, text in connection.execute(
                    "SELECT score, text FROM indicator_anchors_v2 WHERE indicator_id = ? ORDER BY score",
                    (indicator_id,),
                )
            ]
            indicators.append(
                {
                    "database_id": indicator_id,
                    "id": indicator_code,
                    "source_text": source_text,
                    "weight": indicator_weight,
                    "anchors": anchors,
                }
            )
        groups.append(
            {
                "database_id": group_id,
                "id": code,
                "level": level,
                "weight": weight,
                "indicators": indicators,
            }
        )
    config["groups"] = groups
    return config


def get_config(config_id):
    with connect() as connection:
        return _config_detail(connection, config_id)


def get_published_config(skill_code):
    with connect() as connection:
        rubric_id = _current_rubric_id(connection)
        row = connection.execute(
            """SELECT id FROM scoring_configs_v2
            WHERE rubric_id = ? AND skill_code = ? AND status = 'published'
            ORDER BY version DESC LIMIT 1""",
            (rubric_id, skill_code),
        ).fetchone()
        if not row:
            raise V2NotFound("published scoring rubric not found")
        return _config_detail(connection, row[0])


def create_draft(skill_code):
    with connect() as connection:
        rubric_id = _current_rubric_id(connection)
        base = connection.execute(
            """SELECT id FROM scoring_configs_v2
            WHERE rubric_id = ? AND skill_code = ? AND status = 'published'
            ORDER BY version DESC LIMIT 1""",
            (rubric_id, skill_code),
        ).fetchone()
        if not base:
            raise V2NotFound("published rubric not found")
        version = connection.execute(
            "SELECT coalesce(max(version), 0) + 1 FROM scoring_configs_v2 WHERE rubric_id = ? AND skill_code = ?",
            (rubric_id, skill_code),
        ).fetchone()[0]
        config_id = connection.execute(
            """INSERT INTO scoring_configs_v2
            (rubric_id, skill_code, code, version, parent_config_id, status, calibration_status, is_simulated_test_data)
            VALUES (?, ?, ?, ?, ?, 'draft', 'uncalibrated', 1)""",
            (rubric_id, skill_code, f"{skill_code}.v{version}", version, base[0]),
        ).lastrowid
        for group_id, level, code, weight in connection.execute(
            "SELECT id, level, code, weight FROM indicator_groups_v2 WHERE config_id = ? ORDER BY id",
            (base[0],),
        ).fetchall():
            new_group = connection.execute(
                "INSERT INTO indicator_groups_v2 (config_id, skill_code, level, code, weight) VALUES (?, ?, ?, ?, ?)",
                (config_id, skill_code, level, code, weight),
            ).lastrowid
            for indicator_id, indicator_code, source_text, indicator_weight in connection.execute(
                "SELECT id, code, source_text, weight FROM indicators_v2 WHERE group_id = ? ORDER BY id",
                (group_id,),
            ).fetchall():
                new_indicator = connection.execute(
                    "INSERT INTO indicators_v2 (group_id, code, source_text, weight) VALUES (?, ?, ?, ?)",
                    (new_group, indicator_code, source_text, indicator_weight),
                ).lastrowid
                connection.executemany(
                    "INSERT INTO indicator_anchors_v2 (indicator_id, score, text) VALUES (?, ?, ?)",
                    [
                        (new_indicator, score, text)
                        for score, text in connection.execute(
                            "SELECT score, text FROM indicator_anchors_v2 WHERE indicator_id = ? ORDER BY score",
                            (indicator_id,),
                        ).fetchall()
                    ],
                )
        return _config_detail(connection, config_id)


def update_config(config_id, payload):
    with connect() as connection:
        config = _config_detail(connection, config_id)
        if set(payload) == {"status"}:
            target = payload["status"]
            allowed = (
                target == "reviewed" and config["status"] == "draft"
                or target == "archived" and config["status"] in {"draft", "reviewed"}
            )
            if target not in {"reviewed", "archived"}:
                raise V2Invalid("invalid status transition")
            if not allowed:
                raise V2Conflict("invalid status transition")
            connection.execute(
                "UPDATE scoring_configs_v2 SET status = ? WHERE id = ?",
                (target, config_id),
            )
            return _config_detail(connection, config_id)
        if config["status"] != "draft":
            raise V2Conflict("only draft configs can be edited")
        if set(payload) == {"indicator_updates"}:
            for update in payload["indicator_updates"]:
                if not set(update) <= {"indicator_id", "source_text", "weight", "anchors"} or "indicator_id" not in update:
                    raise V2Invalid("invalid indicator update")
                row = connection.execute(
                    """SELECT i.id FROM indicators_v2 i
                    JOIN indicator_groups_v2 g ON g.id = i.group_id
                    WHERE i.id = ? AND g.config_id = ?""",
                    (update["indicator_id"], config_id),
                ).fetchone()
                if not row:
                    raise V2NotFound("indicator not found")
                if "source_text" in update:
                    if not isinstance(update["source_text"], str) or not update["source_text"].strip():
                        raise V2Invalid("invalid source text")
                    connection.execute(
                        "UPDATE indicators_v2 SET source_text = ? WHERE id = ?",
                        (update["source_text"], row[0]),
                    )
                if "weight" in update:
                    if type(update["weight"]) not in {int, float} or update["weight"] <= 0:
                        raise V2Invalid("invalid indicator weight")
                    connection.execute(
                        "UPDATE indicators_v2 SET weight = ? WHERE id = ?",
                        (update["weight"], row[0]),
                    )
                if "anchors" in update:
                    anchors = update["anchors"]
                    if not isinstance(anchors, list) or len(anchors) != 5 or any(not isinstance(text, str) or not text.strip() for text in anchors):
                        raise V2Invalid("exactly five anchors are required")
                    connection.execute(
                        "DELETE FROM indicator_anchors_v2 WHERE indicator_id = ?", (row[0],)
                    )
                    connection.executemany(
                        "INSERT INTO indicator_anchors_v2 (indicator_id, score, text) VALUES (?, ?, ?)",
                        [(row[0], score, text) for score, text in enumerate(anchors)],
                    )
            return _config_detail(connection, config_id)
        if set(payload) == {"group_updates"}:
            for update in payload["group_updates"]:
                if set(update) != {"group_id", "weight"} or type(update["weight"]) not in {int, float} or update["weight"] <= 0:
                    raise V2Invalid("invalid group update")
                changed = connection.execute(
                    "UPDATE indicator_groups_v2 SET weight = ? WHERE id = ? AND config_id = ?",
                    (update["weight"], update["group_id"], config_id),
                )
                if not changed.rowcount:
                    raise V2NotFound("group not found")
            return _config_detail(connection, config_id)
        raise V2Invalid("unsupported config update")


def _validate_config(connection, config_id):
    groups = connection.execute(
        "SELECT id, level, weight FROM indicator_groups_v2 WHERE config_id = ?",
        (config_id,),
    ).fetchall()
    if {level for _id, level, _weight in groups} != set(range(1, 7)):
        raise V2Invalid("all six levels are required")
    for level in range(1, 7):
        if abs(sum(weight for _id, item_level, weight in groups if item_level == level) - 1) > 0.000001:
            raise V2Invalid("group weights must sum to one")
    for group_id, _level, _weight in groups:
        indicators = connection.execute(
            "SELECT id, weight FROM indicators_v2 WHERE group_id = ?", (group_id,)
        ).fetchall()
        if not indicators or abs(sum(weight for _id, weight in indicators) - 1) > 0.000001:
            raise V2Invalid("indicator weights must sum to one")
        if any(
            connection.execute(
                "SELECT count(*) FROM indicator_anchors_v2 WHERE indicator_id = ?", (indicator_id,)
            ).fetchone()[0]
            != 5
            for indicator_id, _weight in indicators
        ):
            raise V2Invalid("each indicator requires five anchors")


def publish_config(config_id):
    with connect() as connection:
        config = _config_detail(connection, config_id)
        if config["status"] != "reviewed":
            raise V2Conflict("config must be reviewed")
        _validate_config(connection, config_id)
        connection.execute(
            "UPDATE scoring_configs_v2 SET status = 'archived' WHERE rubric_id = ? AND skill_code = ? AND status = 'published'",
            (config["rubric_id"], config["skill_code"]),
        )
        connection.execute(
            "UPDATE scoring_configs_v2 SET status = 'published' WHERE id = ?", (config_id,)
        )
        return _config_detail(connection, config_id)


def list_targets(grade=None, term=None, skill_code=None):
    clauses = ["rubric_id = ?"]
    for column, value in (("grade", grade), ("term", term), ("skill_code", skill_code)):
        if value is not None:
            clauses.append(f"{column} = ?")
    query = "SELECT skill_code, grade, term, target_version, target_level, basic, mastery, excellent FROM target_policies_v2"
    query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY skill_code, grade, term, target_version"
    with connect() as connection:
        params = [
            _current_rubric_id(connection),
            *[
                value
                for _column, value in (("grade", grade), ("term", term), ("skill_code", skill_code))
                if value is not None
            ],
        ]
        items = [
            dict(zip(("skill_code", "grade", "term", "target_version", "target_level", "basic", "mastery", "excellent"), row))
            for row in connection.execute(query, params)
        ]
    return {"items": items}


def create_target(grade, term, skill_code, target_level, target_version):
    if type(target_level) is not int or target_level not in range(1, 7) or not isinstance(target_version, str) or not target_version.strip():
        raise V2Invalid("invalid target")
    with connect() as connection:
        rubric_id = _current_rubric_id(connection)
        if not connection.execute(
            "SELECT 1 FROM skills_v2 WHERE rubric_id = ? AND code = ?", (rubric_id, skill_code)
        ).fetchone():
            raise V2NotFound("skill not found")
        default = connection.execute(
            "SELECT basic, mastery, excellent FROM target_policies_v2 WHERE rubric_id = ? AND skill_code = ? ORDER BY id LIMIT 1",
            (rubric_id, skill_code),
        ).fetchone()
        try:
            target_id = connection.execute(
                """INSERT INTO target_policies_v2
                (rubric_id, skill_code, grade, term, target_version, target_level, basic, mastery, excellent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (rubric_id, skill_code, grade, term, target_version, target_level, *default),
            ).lastrowid
        except sqlite3.IntegrityError as exc:
            raise V2Conflict("target version already exists") from exc
        row = connection.execute(
            "SELECT skill_code, grade, term, target_version, target_level, basic, mastery, excellent FROM target_policies_v2 WHERE id = ?",
            (target_id,),
        ).fetchone()
        return dict(
            zip(
                ("skill_code", "grade", "term", "target_version", "target_level", "basic", "mastery", "excellent"),
                row,
            )
        )
