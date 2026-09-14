from fastapi.testclient import TestClient

from app.main import app


def test_v2_current_and_skill_rubric_are_available():
    with TestClient(app) as client:
        assert client.get("/api/v2/rubrics/current").status_code == 200
        response = client.get("/api/v2/skills/YY.S01/scoring-rubric")
    assert response.status_code == 200
    assert len(response.json()["groups"]) == 6
