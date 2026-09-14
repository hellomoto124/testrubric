import json

from fastapi.testclient import TestClient

from app.main import app


def _evidence(client, student_id=1):
    return client.post(
        "/api/evidence",
        json={
            "student_id": student_id,
            "evidence_type": "teacher_observation",
            "text": "模拟测试数据：学生能清楚说明选择、理由和反思。",
        },
    ).json()


def _job(client, key="v2-workflow", student_id=1, evidence_id=None):
    evidence_id = evidence_id or _evidence(client, student_id)["id"]
    return client.post(
        "/api/v2/assessment-jobs",
        json={
            "student_id": student_id,
            "skill_code": "YY.S01",
            "evidence_refs": [evidence_id],
            "context": "课堂合作任务",
            "support_level": "教师仅澄清任务",
            "period": "default",
            "idempotency_key": key,
        },
    )


def test_v2_job_locks_config_target_and_rejects_cross_student_evidence():
    with TestClient(app) as client:
        evidence = _evidence(client, 1)
        created = _job(client, "v2-lock", evidence_id=evidence["id"])
        repeated = _job(client, "v2-lock", evidence_id=evidence["id"])
        rejected = _job(client, "v2-cross", student_id=2, evidence_id=evidence["id"])

    assert created.status_code == repeated.status_code == 201
    assert created.json()["id"] == repeated.json()["id"]
    assert created.json()["config_snapshot"]["status"] == "published"
    assert created.json()["target_snapshot"]["target_level"] == 3
    assert created.json()["rubric_code"] == "kai_feng_yuyang_260910"
    assert rejected.status_code == 422


def test_v2_demo_worker_uses_host_scorer_and_sse_reaches_terminal_state():
    with TestClient(app) as client:
        job = _job(client, "v2-demo-worker").json()

    from app.worker import process_one_job

    completed = process_one_job()
    assert completed["id"] == job["id"]
    assert completed["status"] == "succeeded"
    assert completed["result"]["scoring_version"] == "anchor_interp_v1"
    assert completed["result"]["score_state"] in {"exact", "bounded"}
    assert completed["result"]["feedback"]
    assert [event["stage"] for event in completed["events"]][-5:] == [
        "evidence_extractor",
        "rubric_assessor",
        "host_scoring",
        "feedback_writer",
        "succeeded",
    ]
    with TestClient(app) as client:
        response = client.get(f"/api/v2/assessment-jobs/{job['id']}/events")
    assert response.status_code == 200
    assert "event: status" in response.text
    assert '"status": "succeeded"' in response.text


def test_v2_retry_recovery_and_terminal_failure(monkeypatch):
    from app import worker
    from app.database import connect, get_v2_job, recover_running_jobs_v2

    monkeypatch.setenv("DEMO_AGENT_MODE", "false")
    with TestClient(app) as client:
        job = _job(client, "v2-fail").json()

    def broken(*_args, **_kwargs):
        raise RuntimeError("model failed")

    for _ in range(3):
        assert worker.process_one_job(agent_builder=broken, model_factory=lambda: object()) is None
    failed = get_v2_job(job["id"])
    assert failed["status"] == "failed"
    assert failed["attempts"] == 3

    with connect() as connection:
        connection.execute(
            "UPDATE assessment_jobs_v2 SET status = 'running' WHERE id = ?", (job["id"],)
        )
    assert recover_running_jobs_v2() == 1
    assert get_v2_job(job["id"])["status"] == "queued"


def test_v2_revision_uses_result_id_and_history_excludes_revision_as_growth():
    with TestClient(app) as client:
        _job(client, "v2-revision").json()
    from app.worker import process_one_job

    completed = process_one_job()
    result = completed["result"]
    judgments = result["judgments"]
    judgments[0] = judgments[0] | {"ordinal_score": 3}
    with TestClient(app) as client:
        revised = client.post(
            f"/api/v2/assessments/{result['id']}/revisions",
            json={"judgments": judgments, "reason": "教师复核模拟修订"},
        )
        history = client.get("/api/v2/students/1/skills/YY.S01/history")

    assert revised.status_code == 201, revised.text
    assert revised.json()["revision"] == 2
    assert revised.json()["supersedes_result_id"] == result["id"]
    assert len(history.json()["items"]) == 1
    assert len(history.json()["items"][0]["revisions"]) == 1


def test_v2_job_row_contains_no_model_controlled_score_fields():
    with TestClient(app) as client:
        evidence = _evidence(client)
        payload = {
            "student_id": 1,
            "skill_code": "YY.S01",
            "evidence_refs": [evidence["id"]],
            "context": "课堂",
            "support_level": "无",
            "period": "default",
            "idempotency_key": "v2-extra",
            "total": 500,
        }
        response = client.post("/api/v2/assessment-jobs", json=payload)
    assert response.status_code == 422
    assert "only" in json.dumps(response.json(), ensure_ascii=False)


def test_v2_real_deepagents_graph_runs_three_stages_with_scripted_model(monkeypatch):
    from app.worker import process_one_job
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from pydantic import Field

    monkeypatch.setenv("DEMO_AGENT_MODE", "false")
    with TestClient(app) as client:
        evidence = _evidence(client)
        job = _job(client, "v2-scripted", evidence_id=evidence["id"]).json()

    judgments = []
    for group in job["config_snapshot"]["groups"]:
        for indicator in group["indicators"]:
            judgments.append(
                {
                    "indicator_id": indicator["database_id"],
                    "observation_state": "observed",
                    "ordinal_score": 4 if group["level"] <= 3 else 0,
                    "evidence_refs": [evidence["id"]],
                    "fragment_locator": "全文",
                    "reason": "脚本化模拟判断",
                    "support_context": "无",
                }
            )

    class ScriptedModel(BaseChatModel):
        coordinator_turn: int = 0
        role_turns: dict[str, int] = Field(default_factory=dict)

        @property
        def _llm_type(self):
            return "scripted-v2"

        def _get_ls_params(self, **_kwargs):
            return {"ls_provider": "openai", "ls_model_name": "scripted-v2", "ls_model_type": "chat"}

        def bind_tools(self, _tools, **_kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **_kwargs):
            prompt = "\n".join(str(message.content) for message in messages)
            if "Dispatch evidence_extractor" in prompt:
                if self.coordinator_turn < 3:
                    role = ("evidence_extractor", "rubric_assessor", "feedback_writer")[self.coordinator_turn]
                    self.coordinator_turn += 1
                    return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{"name": "task", "args": {"subagent_type": role, "description": "complete"}, "id": f"task-{self.coordinator_turn}"}]))])
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content="done"))])
            role = (
                "evidence_extractor"
                if "Extract behavior" in prompt
                else "rubric_assessor"
                if "Use extracted evidence" in prompt
                else "feedback_writer"
                if "Read the host result" in prompt
                else ""
            )
            turn = self.role_turns.get(role, 0)
            self.role_turns[role] = turn + 1
            if role == "evidence_extractor" and turn == 0:
                call = {"name": "submit_extraction", "args": {"fragments": [{"evidence_ref": evidence["id"], "behavior": "说明理由", "context": "课堂", "support_level": "无", "opportunity": "一次"}]}, "id": "extract"}
            elif role == "rubric_assessor" and turn == 0:
                call = {"name": "submit_judgments", "args": {"judgments": judgments}, "id": "judge"}
            elif role == "feedback_writer" and turn == 0:
                call = {"name": "read_host_result", "args": {}, "id": "read-score"}
            elif role == "feedback_writer" and turn == 1:
                call = {"name": "submit_feedback", "args": {"feedback": {"feedback": "继续收集跨情境证据。"}}, "id": "feedback"}
            else:
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content="done"))])
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[call]))])

    completed = process_one_job(model_factory=ScriptedModel)
    from app.database import get_v2_job

    assert completed is not None, get_v2_job(job["id"])["error"]
    assert completed["status"] == "succeeded"
    assert completed["result"]["feedback"] == "继续收集跨情境证据。"
    assert completed["result"]["scoring_version"] == "anchor_interp_v1"
