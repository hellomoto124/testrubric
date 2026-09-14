from fastapi.testclient import TestClient

from app.main import app


def test_v2_seed_has_20_students_three_classes_and_228_representative_results():
    from app.database import connect

    with TestClient(app):
        pass
    with connect() as connection:
        counts = (
            connection.execute("SELECT count(*) FROM students").fetchone()[0],
            connection.execute("SELECT count(*) FROM classes").fetchone()[0],
            connection.execute(
                "SELECT count(*) FROM assessment_results_v2 WHERE engine = 'seed_demo_v2'"
            ).fetchone()[0],
        )
        states = {
            row[0]
            for row in connection.execute(
                "SELECT json_extract(result, '$.score_state') FROM assessment_results_v2 WHERE engine = 'seed_demo_v2'"
            )
        }
        target_states = {
            row[0]
            for row in connection.execute(
                "SELECT json_extract(result, '$.target_status') FROM assessment_results_v2 WHERE engine = 'seed_demo_v2'"
            )
        }
    assert counts == (20, 3, 228)
    assert {"exact", "bounded", "insufficient_evidence", "needs_review"} <= states
    assert {"above_target", "below_target", "meets_target"} <= target_states


def test_v2_dashboards_preserve_goal_capability_skill_hierarchy_without_totals():
    with TestClient(app) as client:
        school = client.get("/api/v2/dashboard/school/1")
        classroom = client.get("/api/v2/dashboard/class/1")
        student = client.get("/api/v2/dashboard/student/1")

    assert school.status_code == classroom.status_code == student.status_code == 200
    assert len(school.json()["goals"]) == 3
    assert sum(len(goal["capabilities"]) for goal in school.json()["goals"]) == 10
    assert sum(
        len(capability["skills"])
        for goal in student.json()["goals"]
        for capability in goal["capabilities"]
    ) == 38
    assert school.json()["scope"] == {"type": "school", "id": 1}
    assert classroom.json()["student_count"] == 7
    assert student.json()["subject"]["anonymous_id"] == "模拟学生01"
    assert "total_score" not in str(school.json())
    first_skill = school.json()["goals"][0]["capabilities"][0]["skills"][0]
    assert set(first_skill) >= {
        "code",
        "name",
        "target_level",
        "median_level",
        "coverage",
        "target_status_counts",
    }


def test_v2_dashboard_unknown_scope_or_subject_is_404():
    with TestClient(app) as client:
        assert client.get("/api/v2/dashboard/planet/1").status_code == 404
        assert client.get("/api/v2/dashboard/student/999").status_code == 404


def test_v2_seed_is_idempotent_and_live_result_wins_without_deleting_seed():
    from app.database import connect
    from app.worker import process_one_job

    with TestClient(app) as client:
        evidence = client.post(
            "/api/evidence",
            json={
                "student_id": 1,
                "evidence_type": "teacher_observation",
                "text": "模拟测试数据：新的模型评估证据。",
            },
        ).json()
        client.post(
            "/api/v2/assessment-jobs",
            json={
                "student_id": 1,
                "skill_code": "YY.S01",
                "evidence_refs": [evidence["id"]],
                "idempotency_key": "live-v2-result",
            },
        )
    assert process_one_job()["result"]["engine"] == "demo_deterministic_v2"
    with TestClient(app) as client:
        profile = client.get("/api/v2/dashboard/student/1").json()
    skill = profile["goals"][0]["capabilities"][0]["skills"][0]
    assert skill["result"]["engine"] == "demo_deterministic_v2"
    with connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM assessment_results_v2 WHERE engine = 'seed_demo_v2'"
        ).fetchone()[0] == 228
