from fastapi.testclient import TestClient

from app.main import app


def test_current_rubric_contains_all_future9_skills_and_levels():
    response = TestClient(app).get("/api/rubrics/current")

    assert response.status_code == 200
    rubric = response.json()
    assert rubric["rubric_version"]
    assert rubric["source_url"]
    assert rubric["license_note"]
    assert "local_adaptation" in rubric
    assert len(rubric["competencies"]) == 9
    skills = [skill for competency in rubric["competencies"] for skill in competency["skills"]]
    assert len(skills) == 36
    assert all([level["level"] for level in skill["levels"]] == [1, 2, 3, 4, 5, 6] for skill in skills)
    assert "年级与等级对应关系" not in str(rubric)


def test_seeded_sqlite_contains_only_simulated_school_classes_and_students():
    with TestClient(app):
        from app.database import connect

        with connect() as connection:
            assert connection.execute("SELECT count(*) FROM schools").fetchone()[0] == 1
            assert connection.execute("SELECT count(*) FROM classes").fetchone()[0] == 3
            assert connection.execute("SELECT count(*) FROM students").fetchone()[0] == 30
            assert connection.execute(
                "SELECT count(*) FROM schools WHERE is_simulated_test_data = 1"
            ).fetchone()[0] == 1
            assert connection.execute(
                "SELECT count(*) FROM classes WHERE is_simulated_test_data = 1"
            ).fetchone()[0] == 3
            assert connection.execute(
                "SELECT count(*) FROM students WHERE is_simulated_test_data = 1"
            ).fetchone()[0] == 30
