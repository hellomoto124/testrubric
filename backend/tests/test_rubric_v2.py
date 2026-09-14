def test_v2_migration_is_idempotent_and_keeps_legacy_rows(monkeypatch, tmp_path):
    from app import database
    from app.database import initialize, v2_catalog
    from app.main import RUBRIC

    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "v2.db")
    initialize(RUBRIC)
    initialize(RUBRIC)
    catalog = v2_catalog()

    assert (catalog["goals"], catalog["capabilities"], catalog["skills"], catalog["levels"]) == (3, 10, 38, 228)
    assert catalog["indicators"] >= 228
    assert catalog["legacy_mapping"]["status"] == "legacy_unscored"
