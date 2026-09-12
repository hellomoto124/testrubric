from fastapi.testclient import TestClient

from app.main import RUBRIC, app


def test_startup_seeds_reproducible_non_official_demo_assessments():
    with TestClient(app):
        from app.database import connect, initialize

        with connect() as connection:
            assert connection.execute("SELECT count(*) FROM evidence").fetchone()[0] == 60
            assert connection.execute("SELECT count(*) FROM assessment_jobs").fetchone()[0] == 180
            assert connection.execute("SELECT count(*) FROM assessment_results").fetchone()[0] == 180
            assert connection.execute("SELECT count(*) FROM assessment_jobs WHERE engine = 'seed_demo' AND status = 'succeeded'").fetchone()[0] == 180
            assert connection.execute("SELECT count(*) FROM evidence WHERE text LIKE '%模拟测试数据%AI自动评估%非正式%'").fetchone()[0] == 60
        initialize(RUBRIC)
        with connect() as connection:
            assert connection.execute("SELECT count(*) FROM assessment_jobs").fetchone()[0] == 180


def test_school_dashboard_has_nine_summaries_heatmap_distribution_coverage_and_trend():
    with TestClient(app) as client:
        response = client.get("/api/dashboard/school")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_notice"] == "模拟测试数据；AI自动评估；非正式。"
    assert payload["school"]["is_simulated_test_data"] is True
    assert len(payload["competencies"]) == 9
    assert [item["level"] for item in payload["competencies"]] == [3] * 9
    assert payload["coverage"] == {"assessed_count": 180, "skill_count": 720, "coverage": 0.25}
    assert [item["count"] for item in payload["level_distribution"]] == [27, 36, 36, 27, 27, 27]
    assert [item["class"]["id"] for item in payload["class_heatmap"]] == [1, 2, 3]
    assert payload["trend"]


def test_class_dashboard_profile_and_context_are_stable_and_missing_resources_are_404():
    with TestClient(app) as client:
        context = client.get("/api/demo/context")
        classroom = client.get("/api/classes/1/dashboard")
        profile = client.get("/api/students/1/profile")
        missing_class = client.get("/api/classes/999/dashboard")
        missing_student = client.get("/api/students/999/profile")

    assert context.status_code == 200
    assert [item["id"] for item in context.json()["classes"]] == [1, 2, 3]
    assert len(context.json()["students"]) == 20
    assert classroom.status_code == 200
    assert len(classroom.json()["students"]) == 7
    assert len(classroom.json()["competencies"]) == 9
    assert profile.status_code == 200
    assert len(profile.json()["competencies"]) == 9
    assert len(profile.json()["skills"]) == 36
    assert len(profile.json()["evidence_timeline"]) == 3
    assert missing_class.status_code == 404
    assert missing_student.status_code == 404
