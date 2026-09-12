from app.main import app
from fastapi.testclient import TestClient


def test_current_rubric_contains_all_future9_skills_and_levels():
    with TestClient(app) as client:
        response = client.get("/api/rubrics/current")

    assert response.status_code == 200
    rubric = response.json()
    assert rubric["rubric_version"]
    assert rubric["source_url"]
    assert rubric["source_url"].startswith("https://")
    assert rubric["license_note"]
    assert "local_adaptation" in rubric
    assert len(rubric["competencies"]) == 9
    skills = [skill for competency in rubric["competencies"] for skill in competency["skills"]]
    assert len(skills) == 36
    assert all([level["level"] for level in skill["levels"]] == [1, 2, 3, 4, 5, 6] for skill in skills)
    assert all(
        descriptor not in {"--", "---"}
        for skill in skills
        for level in skill["levels"]
        for descriptor in level["descriptors"]
    )
    assert "年级与等级对应关系" not in str(rubric)


def test_seeded_sqlite_contains_only_simulated_school_classes_and_students():
    with TestClient(app):
        from app.database import connect

        with connect() as connection:
            assert connection.execute("SELECT count(*) FROM schools").fetchone()[0] == 1
            assert connection.execute("SELECT count(*) FROM classes").fetchone()[0] == 3
            assert connection.execute("SELECT count(*) FROM students").fetchone()[0] == 20
            assert connection.execute(
                "SELECT count(*) FROM schools WHERE is_simulated_test_data = 1"
            ).fetchone()[0] == 1
            assert connection.execute(
                "SELECT count(*) FROM classes WHERE is_simulated_test_data = 1"
            ).fetchone()[0] == 3
            assert connection.execute(
                "SELECT count(*) FROM students WHERE is_simulated_test_data = 1"
            ).fetchone()[0] == 20
            assert connection.execute(
                "SELECT class_id, count(*) FROM students GROUP BY class_id ORDER BY class_id"
            ).fetchall() == [(1, 7), (2, 7), (3, 6)]
            assert connection.execute("SELECT count(*) FROM rubrics").fetchone()[0] == 1
            assert connection.execute("SELECT count(*) FROM competencies").fetchone()[0] == 9
            assert connection.execute("SELECT count(*) FROM skills").fetchone()[0] == 36
            assert connection.execute("SELECT count(*) FROM levels").fetchone()[0] == 216
            row = connection.execute(
                "SELECT rubric_version, source_url, license_note, local_adaptation FROM rubrics"
            ).fetchone()
            assert row[0] == "future-9-3"
            assert row[1].startswith("https://")
            assert row[2]
            assert row[3]
