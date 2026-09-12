import pytest


@pytest.fixture(autouse=True)
def temporary_database(monkeypatch, tmp_path):
    """Keep every API test isolated from the runnable demo database."""
    from app import database

    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "app.db")
