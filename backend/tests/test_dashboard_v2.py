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
        "target_score",
        "median_level",
        "coverage",
        "target_status_counts",
        "score_points",
        "score_intervals",
    }
    assert first_skill["target_score"] == first_skill["target_level"] * 100
    assert all(0 <= value <= 600 for value in first_skill["score_points"])
    assert all(item["lower"] <= item["upper"] for item in first_skill["score_intervals"])


def test_v2_dashboard_unknown_scope_or_subject_is_404():
    with TestClient(app) as client:
        assert client.get("/api/v2/dashboard/planet/1").status_code == 404
        assert client.get("/api/v2/dashboard/student/999").status_code == 404


def test_school_dashboard_can_return_student_rows_for_one_selected_skill():
    with TestClient(app) as client:
        response = client.get(
            "/api/v2/dashboard/school/1", params={"skill_code": "YY.S01"}
        )

    assert response.status_code == 200
    rows = response.json()["student_rows"]
    assert len(rows) == 20
    assert rows[0]["anonymous_id"] == "模拟学生01"
    assert rows[0]["class_name"] == "模拟测试班级1"
    assert rows[0]["result"]["score_state"] in {
        "exact",
        "bounded",
        "insufficient_evidence",
        "needs_review",
    }
    assert "judgments" not in rows[0]["result"]
    assert "rank" not in str(rows)


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


def test_v2_seed_never_touches_non_simulated_students_with_or_without_evidence():
    from app.database import connect, initialize
    from app.main import RUBRIC

    with TestClient(app):
        pass
    with connect() as connection:
        connection.executemany(
            "INSERT INTO students (id, class_id, anonymous_id, is_simulated_test_data) VALUES (?, 1, ?, 0)",
            [(21, "真实占位学生21"), (22, "真实占位学生22")],
        )
        connection.execute(
            "INSERT INTO evidence (student_id, evidence_type, text) VALUES (21, 'teacher_observation', '非演示证据')"
        )
    initialize(RUBRIC)
    with connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM assessment_jobs_v2 WHERE student_id IN (21, 22)"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM assessment_results_v2 WHERE engine = 'seed_demo_v2'"
        ).fetchone()[0] == 228
