import sqlite3

import pytest

from app.database import connect, initialize, v2_catalog
from app.main import RUBRIC


def initialize_v2():
    initialize(RUBRIC)


def insert_second_rubric():
    with connect() as connection:
        rubric_id = connection.execute(
            "INSERT INTO rubric_versions_v2 (code, source, scoring_version, is_simulated_test_data) VALUES ('second-version', 'test', 'anchor_interp_v1', 1)"
        ).lastrowid
        goal_id = connection.execute(
            "INSERT INTO education_goals_v2 (rubric_id, code, name) VALUES (?, 'YY.G01', '第二版本目标')",
            (rubric_id,),
        ).lastrowid
        capability_id = connection.execute(
            "INSERT INTO capabilities_v2 (rubric_id, goal_id, code, name, description) VALUES (?, ?, 'YY.C01', '第二版本能力', '测试')",
            (rubric_id, goal_id),
        ).lastrowid
        connection.execute(
            "INSERT INTO skills_v2 (rubric_id, capability_id, code, subskill, name_cn, name_en, source, excel_row) VALUES (?, ?, 'YY.S01', '测试', '第二版本技能', 'Test', 'test', 1)",
            (rubric_id, capability_id),
        )
        config_id = connection.execute(
            "INSERT INTO scoring_configs_v2 (rubric_id, skill_code, code, version, status, calibration_status, is_simulated_test_data) VALUES (?, 'YY.S01', 'YY.S01.demo', 1, 'published', 'uncalibrated', 1)",
            (rubric_id,),
        ).lastrowid
        group_id = connection.execute(
            "INSERT INTO indicator_groups_v2 (config_id, skill_code, level, code) VALUES (?, 'YY.S01', 1, 'YY.S01.L1')",
            (config_id,),
        ).lastrowid
        connection.execute(
            "INSERT INTO indicators_v2 (group_id, code, source_text, weight) VALUES (?, 'YY.S01.L1.I01', '测试', 1)",
            (group_id,),
        )
        connection.execute(
            "INSERT INTO target_policies_v2 (rubric_id, skill_code, grade, term, target_version, target_level) VALUES (?, 'YY.S01', '3-6', 'manual', 'second-target-v1', 4)",
            (rubric_id,),
        )
    return rubric_id


def test_v2_migration_is_idempotent_and_keeps_legacy_rows():
    initialize_v2()
    with connect() as connection:
        legacy_before = tuple(
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("rubrics", "competencies", "skills", "levels")
        )
    initialize_v2()
    with connect() as connection:
        legacy_after = tuple(
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("rubrics", "competencies", "skills", "levels")
        )
    assert legacy_after == legacy_before == (1, 9, 36, 216)
    catalog = v2_catalog()
    assert (catalog["goals"], catalog["capabilities"], catalog["skills"], catalog["levels"]) == (3, 10, 38, 228)
    assert catalog["legacy_mapping"] == {"status": "legacy_unscored"}


def test_foreign_keys_are_enabled_and_reject_invalid_children():
    initialize_v2()
    with connect() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO skills_v2 (rubric_id, capability_id, code, subskill, name_cn, name_en, source, excel_row) VALUES (999, 999, 'bad', 'bad', 'bad', 'bad', 'bad', 1)"
            )


def test_second_rubric_can_reuse_every_stable_code():
    initialize_v2()
    rubric_id = insert_second_rubric()
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM education_goals_v2 WHERE code = 'YY.G01'").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM capabilities_v2 WHERE code = 'YY.C01'").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM skills_v2 WHERE code = 'YY.S01'").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM scoring_configs_v2 WHERE code = 'YY.S01.demo'").fetchone()[0] == 2
        assert connection.execute(
            "SELECT count(*) FROM target_policies_v2 WHERE rubric_id = ?", (rubric_id,)
        ).fetchone()[0] == 1


def test_reinitialize_preserves_second_rubric_and_manual_target():
    initialize_v2()
    rubric_id = insert_second_rubric()
    initialize_v2()
    with connect() as connection:
        assert connection.execute("SELECT code FROM rubric_versions_v2 WHERE id = ?", (rubric_id,)).fetchone() == ("second-version",)
        assert connection.execute(
            "SELECT target_level FROM target_policies_v2 WHERE rubric_id = ? AND target_version = 'second-target-v1'",
            (rubric_id,),
        ).fetchone() == (4,)


def test_current_catalog_excludes_other_rubric_versions():
    initialize_v2()
    insert_second_rubric()
    catalog = v2_catalog()
    assert (catalog["goals"], catalog["capabilities"], catalog["skills"], catalog["levels"]) == (3, 10, 38, 228)


def test_all_38_demo_configs_are_published_uncalibrated_and_simulated():
    initialize_v2()
    with connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM scoring_configs_v2 WHERE status = 'published' AND calibration_status = 'uncalibrated' AND is_simulated_test_data = 1"
        ).fetchone()[0] == 38


def test_every_indicator_has_five_anchors_and_group_weights_sum_to_one():
    initialize_v2()
    with connect() as connection:
        indicators = connection.execute("SELECT count(*) FROM indicators_v2").fetchone()[0]
        anchors = connection.execute("SELECT count(*) FROM indicator_anchors_v2").fetchone()[0]
        bad_anchor_counts = connection.execute(
            "SELECT count(*) FROM (SELECT indicator_id FROM indicator_anchors_v2 GROUP BY indicator_id HAVING count(*) != 5)"
        ).fetchone()[0]
        bad_weights = connection.execute(
            "SELECT count(*) FROM (SELECT group_id FROM indicators_v2 GROUP BY group_id HAVING abs(sum(weight) - 1.0) > 0.000001)"
        ).fetchone()[0]
    assert indicators > 228
    assert anchors == indicators * 5
    assert bad_anchor_counts == 0
    assert bad_weights == 0


def test_school_name_and_local_target_policy_are_explicit():
    initialize_v2()
    with connect() as connection:
        assert connection.execute("SELECT name FROM schools WHERE is_simulated_test_data = 1").fetchone() == ("凯风雨旸小学（模拟测试数据）",)
        assert connection.execute(
            "SELECT count(*) FROM target_policies_v2 WHERE grade = '3-6' AND target_level = 3 AND basic = 2 AND mastery = 3 AND excellent = 4 AND target_version = 'yy-grade3-6-default-v1'"
        ).fetchone()[0] == 38


def test_generated_prerelease_schema_is_rebuilt_once():
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE rubric_versions_v2 (id INTEGER PRIMARY KEY, code TEXT UNIQUE, source TEXT, scoring_version TEXT, is_simulated_test_data INTEGER);
            CREATE TABLE capabilities_v2 (id INTEGER PRIMARY KEY, rubric_id INTEGER, goal_id INTEGER, code TEXT UNIQUE, name TEXT, description TEXT);
            CREATE TABLE scoring_configs_v2 (id INTEGER PRIMARY KEY, rubric_id INTEGER, code TEXT UNIQUE, status TEXT, calibration_status TEXT, is_simulated_test_data INTEGER);
            INSERT INTO rubric_versions_v2 VALUES (1, 'old-generated', 'old', 'anchor_interp_v1', 1);
            INSERT INTO scoring_configs_v2 VALUES (1, 1, 'YY.S01.demo', 'published', 'uncalibrated', 1);
            """
        )
    initialize_v2()
    assert v2_catalog()["skills"] == 38


def test_prerelease_schema_with_non_generated_data_is_not_deleted():
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE rubric_versions_v2 (id INTEGER PRIMARY KEY, code TEXT UNIQUE, source TEXT, scoring_version TEXT, is_simulated_test_data INTEGER);
            CREATE TABLE capabilities_v2 (id INTEGER PRIMARY KEY, rubric_id INTEGER, goal_id INTEGER, code TEXT UNIQUE, name TEXT, description TEXT);
            CREATE TABLE scoring_configs_v2 (id INTEGER PRIMARY KEY, rubric_id INTEGER, code TEXT UNIQUE, status TEXT, calibration_status TEXT, is_simulated_test_data INTEGER);
            INSERT INTO rubric_versions_v2 VALUES (1, 'manual-version', 'manual', 'anchor_interp_v1', 0);
            INSERT INTO scoring_configs_v2 VALUES (1, 1, 'manual', 'draft', 'uncalibrated', 0);
            """
        )
    with pytest.raises(RuntimeError, match="non-generated data"):
        initialize_v2()
    with connect() as connection:
        assert connection.execute("SELECT code FROM rubric_versions_v2").fetchone() == ("manual-version",)
