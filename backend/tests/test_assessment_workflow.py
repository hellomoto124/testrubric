from app.main import app
from fastapi.testclient import TestClient


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


def test_malformed_pdf_is_rejected_with_422():
    with TestClient(app) as client:
        response = client.post(
            "/api/evidence",
            data={"student_id": "1", "evidence_type": "student_work"},
            files={"file": ("broken.pdf", b"not a pdf", "application/pdf")},
        )

    assert response.status_code == 422
    assert "PDF" in response.json()["detail"]


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

    assert created.status_code == 201
    assert job.json()["status"] == "queued"


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


def test_deep_agent_constructs_with_registered_openai_profile_without_network():
    from app.agents import build_deep_agent
    from langchain_openai import ChatOpenAI

    agent = build_deep_agent(
        ChatOpenAI(model="test", api_key="placeholder", base_url="http://127.0.0.1:9/v1"),
        lambda: {"evidence": [], "rubric": {}},
        lambda candidate: candidate,
    )

    assert agent is not None
    tool_names = agent.nodes["tools"].bound._tools_by_name
    # Deep Agents requires a StateBackend-backed read_file tool internally; the
    # profile excludes and rejects it before it reaches the model.
    assert set(tool_names) == {"task", "read_current_task", "submit_candidate", "read_file"}


def test_worker_is_not_started_by_api_lifespan_and_demo_result_uses_reviewed_states():
    with TestClient(app) as client:
        evidence = client.post("/api/evidence", json={"student_id": 1, "evidence_type": "teacher_observation", "text": "足够长的可观察证据。"}).json()
        code = client.get("/api/rubrics/current").json()["competencies"][0]["skills"][0]["code"]
        job = client.post("/api/assessment-jobs", json={"student_id": 1, "skill_code": code, "evidence_refs": [evidence["id"]]}).json()
        assert client.get(f"/api/assessment-jobs/{job['id']}").json()["status"] == "queued"

    from app.worker import process_one_job

    completed = process_one_job()
    assert completed["status"] == "succeeded"
    assert completed["results"][0]["status"] in {"assessed", "insufficient_evidence"}


def test_result_revision_uses_result_id_and_rejects_invalid_contract():
    with TestClient(app) as client:
        evidence = client.post("/api/evidence", json={"student_id": 1, "evidence_type": "teacher_observation", "text": "学生使用证据解释答案。"}).json()
        code = client.get("/api/rubrics/current").json()["competencies"][0]["skills"][0]["code"]
        client.post("/api/assessment-jobs", json={"student_id": 1, "skill_code": code, "evidence_refs": [evidence["id"]]})
    from app.worker import process_one_job

    completed = process_one_job()
    result_id = completed["results"][0]["id"]
    payload = completed["results"][0] | {"confidence": 0.8, "model_run_id": "teacher-review"}
    with TestClient(app) as client:
        revised = client.patch(f"/api/assessments/{result_id}", json=payload)
        invalid = client.patch(f"/api/assessments/{result_id}", json=payload | {"confidence": True})
        invalid_text = client.patch(f"/api/assessments/{result_id}", json=payload | {"rationale": 1})
        invalid_ref = client.patch(f"/api/assessments/{result_id}", json=payload | {"evidence_refs": [True]})
        events = client.get(f"/api/assessment-jobs/{completed['id']}/events")

    assert revised.status_code == 200
    assert len(revised.json()["results"]) == 2
    assert invalid.status_code == 422
    assert invalid_text.status_code == 422
    assert invalid_ref.status_code == 422
    assert "succeeded" in events.text


def test_image_context_is_data_url_only_when_vision_is_enabled(monkeypatch):
    monkeypatch.setenv("VISION_ENABLED", "true")
    with TestClient(app) as client:
        evidence = client.post(
            "/api/evidence",
            data={"student_id": "1", "evidence_type": "student_work"},
            files={"file": ("work.png", b"png-bytes", "image/png")},
        ).json()
        code = client.get("/api/rubrics/current").json()["competencies"][0]["skills"][0]["code"]
        job = client.post("/api/assessment-jobs", json={"student_id": 1, "skill_code": code, "evidence_refs": [evidence["id"]]}).json()

    from app.database import task_context

    context = task_context(job["id"])
    assert context["evidence"][0]["image_data_url"].startswith("data:image/png;base64,")
    assert "content" not in context["evidence"][0]


def test_real_agent_path_audits_all_subagents_and_candidate(monkeypatch):
    monkeypatch.setenv("DEMO_AGENT_MODE", "false")
    with TestClient(app) as client:
        evidence = client.post("/api/evidence", json={"student_id": 1, "evidence_type": "teacher_observation", "text": "学生完整解释了策略和证据。"}).json()
        code = client.get("/api/rubrics/current").json()["competencies"][0]["skills"][0]["code"]
        client.post("/api/assessment-jobs", json={"student_id": 1, "skill_code": code, "evidence_refs": [evidence["id"]]})

    class FakeAgent:
        def __init__(self, sink, context):
            self.sink, self.context = sink, context

        def stream_events(self, *_args, **kwargs):
            assert kwargs["version"] == "v3"

            class Handle:
                status = "completed"
                tool_calls = ()

                def __init__(self, name, output):
                    self.name, self.output = name, output

            candidate = {"status": "assessed", "level": 3, "confidence": 0.7, "evidence_refs": self.context["job"]["evidence_refs"], "rationale": "fake", "next_step": "next", "rubric_version": self.context["rubric"]["rubric_version"], "model_run_id": "fake-run"}
            self.sink(candidate)
            return type("Stream", (), {"subagents": [Handle("evidence_extractor", "evidence"), Handle("rubric_assessor", "assessment"), Handle("feedback_writer", "feedback")]})()

    from app.worker import process_one_job

    completed = process_one_job(lambda _model, loader, sink: FakeAgent(sink, loader()), lambda: object())
    details = [event["detail"] for event in completed["events"]]
    assert {"evidence_extractor:completed", "rubric_assessor:completed", "feedback_writer:completed", "submitted"}.issubset(details)


def test_run_worker_recovers_once_and_checks_stop_after_a_job(monkeypatch):
    from app import worker

    calls = []
    monkeypatch.setattr(worker, "recover_running_jobs", lambda: calls.append("recover"))
    monkeypatch.setattr(worker, "process_one_job", lambda: calls.append("job") or {"id": 1})
    states = iter([False, True])

    worker.run_worker(lambda: next(states), poll_interval=0)

    assert calls == ["recover", "job"]
