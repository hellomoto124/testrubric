def test_v2_migration_is_idempotent_and_keeps_legacy_rows(monkeypatch, tmp_path):
    from app import database
    from app.database import initialize, v2_catalog
    from app.main import RUBRIC

    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "v2.db")
    initialize(RUBRIC)
    initialize(RUBRIC)
    catalog = v2_catalog()

    assert (
        catalog["goals"],
        catalog["capabilities"],
        catalog["skills"],
        catalog["levels"],
    ) == (3, 10, 38, 228)
    assert catalog["indicators"] >= 228
    assert catalog["legacy_mapping"]["status"] == "legacy_unscored"
    assert len(catalog["hierarchy"]) == 3
    assert sum(len(goal["capabilities"]) for goal in catalog["hierarchy"]) == 10
    assert (
        sum(
            len(capability["skills"])
            for goal in catalog["hierarchy"]
            for capability in goal["capabilities"]
        )
        == 38
    )


def test_foreign_keys_on_invalid_child(monkeypatch, tmp_path):
    import sqlite3
    import pytest
    from app import database
    from app.database import connect, initialize
    from app.main import RUBRIC
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "fk.db")
    initialize(RUBRIC)
    with connect() as c:
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("INSERT INTO skills_v2 (rubric_id, capability_id, code, subskill, name_cn, name_en, source, excel_row) VALUES (9,9,'x','x','x','x','x',1)")


def test_38_configs_published_uncalibrated_simulated(monkeypatch, tmp_path):
    from app import database
    from app.database import connect, initialize
    from app.main import RUBRIC
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "config.db")
    initialize(RUBRIC)
    with connect() as c:
        assert c.execute("SELECT count(*) FROM scoring_configs_v2 WHERE status='published' AND calibration_status='uncalibrated' AND is_simulated_test_data=1").fetchone()[0] == 38


def test_anchors_count(monkeypatch, tmp_path):
    from app import database
    from app.database import connect, initialize
    from app.main import RUBRIC
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "anchors.db")
    initialize(RUBRIC)
    with connect() as c:
        assert c.execute("SELECT count(*) FROM indicator_anchors_v2").fetchone()[0] == c.execute("SELECT count(*) FROM indicators_v2").fetchone()[0] * 5
