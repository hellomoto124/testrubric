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


def test_drill_down_records_are_explicitly_simulated():
    with TestClient(app) as client:
        school = client.get("/api/dashboard/school").json()
        classroom = client.get("/api/classes/1/dashboard").json()
        context = client.get("/api/demo/context").json()
        profile = client.get("/api/students/1/profile").json()

    assert all(item["class"]["is_simulated_test_data"] is True for item in school["class_heatmap"])
    assert all(item["is_simulated_test_data"] is True for item in classroom["students"])
    assert all(item["is_simulated_test_data"] is True for item in context["classes"])
    assert all(item["is_simulated_test_data"] is True for item in context["students"])
    assert profile["student"]["is_simulated_test_data"] is True


def test_existing_non_seed_result_keeps_priority_while_initialize_backfills_demo_baseline():
    from app.database import DEMO_NOTICE, append_result, connect, create_evidence, create_job, initialize, student_profile

    with TestClient(app):
        with connect() as connection:
            connection.execute("DELETE FROM job_events")
            connection.execute("DELETE FROM assessment_results")
            connection.execute("DELETE FROM assessment_jobs")
            connection.execute("DELETE FROM evidence")
        evidence = create_evidence(1, "teacher_observation", "已有的正式观察证据")
        skill_code = RUBRIC["competencies"][0]["skills"][0]["code"]
        job = create_job(1, skill_code, [evidence["id"]])
        append_result(
            job["id"],
            {
                "status": "assessed",
                "level": 6,
                "confidence": 0.9,
                "evidence_refs": [evidence["id"]],
                "rationale": "教师复核结果。",
                "next_step": "继续保持。",
                "rubric_version": RUBRIC["rubric_version"],
                "model_run_id": "teacher-reviewed-1",
            },
            "teacher_review",
        )
        initialize(RUBRIC)
        with connect() as connection:
            assert connection.execute("SELECT count(*) FROM assessment_jobs WHERE engine = 'seed_demo'").fetchone()[0] == 180
            assert connection.execute("SELECT count(*) FROM assessment_results").fetchone()[0] == 181
            assert connection.execute("SELECT count(*) FROM evidence WHERE text LIKE ?", (f"{DEMO_NOTICE}%",)).fetchone()[0] == 60
            assert connection.execute(
                "SELECT student_id, count(*), count(DISTINCT evidence_type) FROM evidence WHERE text LIKE ? GROUP BY student_id ORDER BY student_id",
                (f"{DEMO_NOTICE}%",),
            ).fetchall() == [(student_id, 3, 3) for student_id in range(1, 21)]
            before = connection.execute("SELECT count(*) FROM assessment_jobs").fetchone()[0]
        initialize(RUBRIC)
        with connect() as connection:
            assert connection.execute("SELECT count(*) FROM assessment_jobs").fetchone()[0] == before

    result = next(item["result"] for item in student_profile(1)["skills"] if item["code"] == skill_code)
    assert result["engine"] == "teacher_review"
    assert result["level"] == 6
