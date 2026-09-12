from fastapi.testclient import TestClient

from app.main import app


def test_evidence_upload_persists_text_for_a_simulated_student():
    with TestClient(app) as client:
        response = client.post(
            "/api/evidence",
            data={
                "student_id": "1",
                "evidence_type": "teacher_observation",
                "text": "学生能解释自己的解题过程。",
            },
        )

    assert response.status_code == 201
    evidence = response.json()
    assert evidence["id"]
    assert evidence["student_id"] == 1
    assert evidence["evidence_type"] == "teacher_observation"
    assert evidence["text"] == "学生能解释自己的解题过程。"


def test_evidence_upload_accepts_txt_student_work():
    with TestClient(app) as client:
        response = client.post(
            "/api/evidence",
            data={"student_id": "1", "evidence_type": "student_work"},
            files={"file": ("work.txt", "我的解题过程", "text/plain")},
        )

    assert response.status_code == 201
    assert response.json()["filename"] == "work.txt"
    assert response.json()["text"] == "我的解题过程"


def test_assessment_job_is_queued_and_persisted_with_sse_event():
    with TestClient(app) as client:
        evidence = client.post(
            "/api/evidence",
            json={"student_id": 1, "evidence_type": "student_self_reflection", "text": "我能说明为什么这个答案正确。"},
        ).json()
        skill_code = client.get("/api/rubrics/current").json()["competencies"][0]["skills"][0]["code"]
        created = client.post(
            "/api/assessment-jobs",
            json={"student_id": 1, "skill_code": skill_code, "evidence_refs": [evidence["id"]]},
        )
        job = client.get(f"/api/assessment-jobs/{created.json()['id']}")
        events = client.get(f"/api/assessment-jobs/{created.json()['id']}/events")

    assert created.status_code == 201
    assert job.json()["status"] in {"queued", "running", "completed"}
    assert "event: status" in events.text


def test_deep_agent_receives_exactly_the_three_restricted_subagents():
    from app.agents import build_deep_agent

    captured = {}
    build_deep_agent(
        model="test-model",
        task_loader=lambda: {"evidence": [], "rubric": {}},
        candidate_sink=lambda candidate: candidate,
        creator=lambda **kwargs: captured.update(kwargs) or "agent",
    )

    assert [agent["name"] for agent in captured["subagents"]] == ["evidence_extractor", "rubric_assessor", "feedback_writer"]
    assert {tool.name for tool in captured["tools"]} == {"read_current_task", "submit_candidate"}
    assert all({tool.name for tool in agent["tools"]} == {"read_current_task", "submit_candidate"} for agent in captured["subagents"])
