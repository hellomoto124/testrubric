from fastapi.testclient import TestClient

from app.main import app


def test_v2_job_locks_config_and_reuses_idempotency_key():
    with TestClient(app) as client:
        evidence = client.post(
            "/api/evidence",
            json={"student_id": 1, "evidence_type": "teacher_observation", "text": "模拟测试证据：能清楚说明自己的选择。"},
        ).json()
        payload = {"student_id": 1, "skill_code": "YY.S01", "evidence_refs": [evidence["id"]], "idempotency_key": "v2-demo-1"}
        created = client.post("/api/v2/assessment-jobs", json=payload)
        repeated = client.post("/api/v2/assessment-jobs", json=payload)

    assert created.status_code == 201
    assert repeated.status_code == 201
    assert created.json()["id"] == repeated.json()["id"]
    assert created.json()["config_snapshot"]["status"] == "published"
    assert created.json()["scoring_version"] == "anchor_interp_v1"


def test_v2_revision_is_append_only_and_history_keeps_it():
    with TestClient(app) as client:
        evidence = client.post("/api/evidence", json={"student_id": 1, "evidence_type": "teacher_observation", "text": "模拟测试证据：能说明理由。"}).json()
        client.post("/api/v2/assessment-jobs", json={"student_id": 1, "skill_code": "YY.S01", "evidence_refs": [evidence["id"]], "idempotency_key": "v2-demo-2"}).json()
    from app.worker import process_one_job

    completed = process_one_job()
    result = completed["result"]
    with TestClient(app) as client:
        revised = client.post(
            f"/api/v2/assessments/{result['id']}/revisions",
            json={"judgments": result["judgments"], "reason": "人工修订"},
        )
        history = client.get("/api/v2/students/1/skills/YY.S01/history")

    assert revised.status_code == 201
    assert revised.json()["revision"] == 2
    assert history.status_code == 200
    assert history.json()["items"][-1]["result"]["revision"] == 2
