def test_database_path_uses_explicit_e2e_environment(monkeypatch, tmp_path):
    from app.database import database_path

    target = tmp_path / "dedicated-e2e.db"
    monkeypatch.setenv("FUTURE9_DATABASE_PATH", str(target))

    assert database_path() == target
