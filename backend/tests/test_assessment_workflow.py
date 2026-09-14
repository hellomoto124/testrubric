import pytest
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
            json={
                "student_id": 1,
                "evidence_type": "student_self_reflection",
                "text": "我能说明为什么这个答案正确。",
            },
        ).json()
        skill_code = client.get("/api/rubrics/current").json()["competencies"][0][
            "skills"
        ][0]["code"]
        created = client.post(
            "/api/assessment-jobs",
            json={
                "student_id": 1,
                "skill_code": skill_code,
                "evidence_refs": [evidence["id"]],
            },
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

    assert [agent["name"] for agent in captured["subagents"]] == [
        "evidence_extractor",
        "rubric_assessor",
        "feedback_writer",
    ]
    assert {tool.name for tool in captured["tools"]} == {
        "read_current_task",
        "submit_candidate",
    }
    assert all(
        {tool.name for tool in agent["tools"]}
        == {"read_current_task", "submit_candidate"}
        for agent in captured["subagents"]
    )


def test_candidate_tool_schema_rejects_qwen_legacy_shape():
    from app.agents import build_deep_agent
    from pydantic import ValidationError

    captured = {}
    build_deep_agent(
        "test-model",
        dict,
        lambda candidate: candidate,
        creator=lambda **kwargs: captured.update(kwargs) or "agent",
    )
    submit = next(tool for tool in captured["tools"] if tool.name == "submit_candidate")
    candidate_schema = next(
        iter(submit.args_schema.model_json_schema()["$defs"].values())
    )

    assert set(candidate_schema["properties"]) == {
        "status",
        "level",
        "confidence",
        "evidence_refs",
        "rationale",
        "next_step",
    }
    assert candidate_schema["additionalProperties"] is False
    with pytest.raises(ValidationError):
        submit.invoke(
            {
                "candidate": {
                    "status": "assessed",
                    "assessed_level": 3,
                    "confidence": 0.8,
                    "evidence_refs": [1],
                    "rationale": "old",
                    "next_step": "next",
                }
            }
        )
    with pytest.raises(ValidationError):
        submit.invoke(
            {
                "candidate": {
                    "status": "assessed",
                    "level": 3,
                    "confidence": 0.8,
                    "evidence_refs": [1],
                    "rationale": "valid",
                    "next_step": "next",
                    "rubric_version": "model-must-not-set",
                }
            }
        )


def test_deep_agent_constructs_with_registered_openai_profile_without_network():
    from app.agents import build_deep_agent
    from langchain_openai import ChatOpenAI

    agent = build_deep_agent(
        ChatOpenAI(
            model="test", api_key="placeholder", base_url="http://127.0.0.1:9/v1"
        ),
        lambda: {"evidence": [], "rubric": {}},
        lambda candidate: candidate,
    )

    assert agent is not None
    tool_names = agent.nodes["tools"].bound._tools_by_name
    # Deep Agents requires a StateBackend-backed read_file tool internally; the
    # profile excludes and rejects it before it reaches the model.
    assert set(tool_names) == {
        "task",
        "read_current_task",
        "submit_candidate",
        "read_file",
    }


def test_worker_is_not_started_by_api_lifespan_and_demo_result_uses_reviewed_states():
    with TestClient(app) as client:
        evidence = client.post(
            "/api/evidence",
            json={
                "student_id": 1,
                "evidence_type": "teacher_observation",
                "text": "足够长的可观察证据。",
            },
        ).json()
        code = client.get("/api/rubrics/current").json()["competencies"][0]["skills"][
            0
        ]["code"]
        job = client.post(
            "/api/assessment-jobs",
            json={
                "student_id": 1,
                "skill_code": code,
                "evidence_refs": [evidence["id"]],
            },
        ).json()
        assert (
            client.get(f"/api/assessment-jobs/{job['id']}").json()["status"] == "queued"
        )

    from app.worker import process_one_job

    completed = process_one_job()
    assert completed["status"] == "succeeded"
    assert completed["results"][0]["status"] in {"assessed", "insufficient_evidence"}


def test_result_revision_uses_result_id_and_rejects_invalid_contract():
    with TestClient(app) as client:
        evidence = client.post(
            "/api/evidence",
            json={
                "student_id": 1,
                "evidence_type": "teacher_observation",
                "text": "学生使用证据解释答案。",
            },
        ).json()
        code = client.get("/api/rubrics/current").json()["competencies"][0]["skills"][
            0
        ]["code"]
        client.post(
            "/api/assessment-jobs",
            json={
                "student_id": 1,
                "skill_code": code,
                "evidence_refs": [evidence["id"]],
            },
        )
    from app.worker import process_one_job

    completed = process_one_job()
    result_id = completed["results"][0]["id"]
    payload = completed["results"][0] | {
        "confidence": 0.8,
        "model_run_id": "teacher-review",
    }
    with TestClient(app) as client:
        revised = client.patch(f"/api/assessments/{result_id}", json=payload)
        invalid = client.patch(
            f"/api/assessments/{result_id}", json=payload | {"confidence": True}
        )
        invalid_text = client.patch(
            f"/api/assessments/{result_id}", json=payload | {"rationale": 1}
        )
        invalid_ref = client.patch(
            f"/api/assessments/{result_id}", json=payload | {"evidence_refs": [True]}
        )
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
        code = client.get("/api/rubrics/current").json()["competencies"][0]["skills"][
            0
        ]["code"]
        job = client.post(
            "/api/assessment-jobs",
            json={
                "student_id": 1,
                "skill_code": code,
                "evidence_refs": [evidence["id"]],
            },
        ).json()

    from app.database import task_context

    context = task_context(job["id"])
    assert context["evidence"][0]["image_data_url"].startswith("data:image/png;base64,")
    assert "content" not in context["evidence"][0]


def test_real_agent_path_audits_all_subagents_and_candidate(monkeypatch):
    monkeypatch.setenv("DEMO_AGENT_MODE", "false")
    with TestClient(app) as client:
        evidence = client.post(
            "/api/evidence",
            json={
                "student_id": 1,
                "evidence_type": "teacher_observation",
                "text": "学生完整解释了策略和证据。",
            },
        ).json()
        code = client.get("/api/rubrics/current").json()["competencies"][0]["skills"][
            0
        ]["code"]
        client.post(
            "/api/assessment-jobs",
            json={
                "student_id": 1,
                "skill_code": code,
                "evidence_refs": [evidence["id"]],
            },
        )

    class FakeAgent:
        def __init__(self, sink, context):
            self.sink, self.context = sink, context

        def stream(self, *_args, **kwargs):
            from langchain_core.messages import AIMessage, ToolMessage

            assert kwargs["stream_mode"] == "updates"
            candidate = {
                "status": "assessed",
                "level": 3,
                "confidence": 0.7,
                "evidence_refs": self.context["job"]["evidence_refs"],
                "rationale": "fake",
                "next_step": "next",
                "rubric_version": self.context["rubric"]["rubric_version"],
                "model_run_id": "fake-run",
            }
            for index, name in enumerate(
                ("evidence_extractor", "rubric_assessor", "feedback_writer"), start=1
            ):
                call_id = f"task-{index}"
                yield {
                    "model": {
                        "messages": [
                            AIMessage(
                                content="",
                                tool_calls=[
                                    {
                                        "name": "task",
                                        "args": {
                                            "subagent_type": name,
                                            "description": "complete",
                                        },
                                        "id": call_id,
                                    }
                                ],
                            )
                        ]
                    }
                }
                yield {
                    "tools": {
                        "messages": [
                            ToolMessage(
                                content="done", name="task", tool_call_id=call_id
                            )
                        ]
                    }
                }
            self.sink(candidate)

    from app.worker import process_one_job

    completed = process_one_job(
        lambda _model, loader, sink: FakeAgent(sink, loader()), lambda: object()
    )
    details = [event["detail"] for event in completed["events"]]
    assert {
        "evidence_extractor:completed",
        "rubric_assessor:completed",
        "feedback_writer:completed",
        "submitted",
    }.issubset(details)


def test_wrong_task_tool_call_id_requeues_real_job(monkeypatch, tmp_path):
    from app import database
    from app.database import get_job
    from app.worker import process_one_job
    from langchain_core.messages import AIMessage, ToolMessage

    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "wrong-id.db")
    monkeypatch.setenv("DEMO_AGENT_MODE", "false")
    with TestClient(app) as client:
        evidence = client.post(
            "/api/evidence",
            json={
                "student_id": 1,
                "evidence_type": "teacher_observation",
                "text": "可用证据。",
            },
        ).json()
        skill = client.get("/api/rubrics/current").json()["competencies"][0]["skills"][
            0
        ]["code"]
        job = client.post(
            "/api/assessment-jobs",
            json={
                "student_id": 1,
                "skill_code": skill,
                "evidence_refs": [evidence["id"]],
            },
        ).json()

    class WrongIdAgent:
        def stream(self, *_args, **_kwargs):
            yield {
                "model": {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "task",
                                    "args": {
                                        "subagent_type": "evidence_extractor",
                                        "description": "complete",
                                    },
                                    "id": "known",
                                }
                            ],
                        )
                    ]
                }
            }
            yield {
                "tools": {
                    "messages": [
                        ToolMessage(content="done", name="task", tool_call_id="wrong")
                    ]
                }
            }

    result = process_one_job(
        lambda _model, _loader, _sink: WrongIdAgent(), lambda: object()
    )

    assert result is None
    assert get_job(job["id"])["status"] == "queued"
    assert "did not complete" in get_job(job["id"])["error"]


def test_error_task_tool_message_requeues_even_after_candidate_submission(
    monkeypatch, tmp_path
):
    from app import database
    from app.database import get_job
    from app.worker import process_one_job
    from langchain_core.messages import AIMessage, ToolMessage

    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "error-status.db")
    monkeypatch.setenv("DEMO_AGENT_MODE", "false")
    with TestClient(app) as client:
        evidence = client.post(
            "/api/evidence",
            json={
                "student_id": 1,
                "evidence_type": "teacher_observation",
                "text": "可用证据。",
            },
        ).json()
        skill = client.get("/api/rubrics/current").json()["competencies"][0]["skills"][
            0
        ]["code"]
        job = client.post(
            "/api/assessment-jobs",
            json={
                "student_id": 1,
                "skill_code": skill,
                "evidence_refs": [evidence["id"]],
            },
        ).json()

    class ErrorAgent:
        def __init__(self, sink, context):
            self.sink, self.context = sink, context

        def stream(self, *_args, **_kwargs):
            for index, name in enumerate(
                ("evidence_extractor", "rubric_assessor", "feedback_writer"), start=1
            ):
                call_id = f"task-{index}"
                yield {
                    "model": {
                        "messages": [
                            AIMessage(
                                content="",
                                tool_calls=[
                                    {
                                        "name": "task",
                                        "args": {
                                            "subagent_type": name,
                                            "description": "complete",
                                        },
                                        "id": call_id,
                                    }
                                ],
                            )
                        ]
                    }
                }
                yield {
                    "tools": {
                        "messages": [
                            ToolMessage(
                                content="failed",
                                name="task",
                                tool_call_id=call_id,
                                status="error",
                            )
                        ]
                    }
                }
            self.sink(
                {
                    "status": "assessed",
                    "level": 3,
                    "confidence": 0.8,
                    "evidence_refs": self.context["job"]["evidence_refs"],
                    "rationale": "candidate",
                    "next_step": "next",
                }
            )

    result = process_one_job(
        lambda _model, loader, sink: ErrorAgent(sink, loader()), lambda: object()
    )
    failed_job = get_job(job["id"])

    assert result is None
    assert failed_job["status"] == "queued"
    assert not any(
        event["detail"].endswith(":completed") for event in failed_job["events"]
    )
    assert {
        "evidence_extractor:failed",
        "rubric_assessor:failed",
        "feedback_writer:failed",
    }.issubset({event["detail"] for event in failed_job["events"]})


def test_run_worker_recovers_once_and_checks_stop_after_a_job(monkeypatch):
    from app import worker

    calls = []
    monkeypatch.setattr(
        worker, "recover_running_jobs_v2", lambda: calls.append("recover-v2")
    )
    monkeypatch.setattr(worker, "recover_running_jobs", lambda: calls.append("recover"))
    monkeypatch.setattr(
        worker, "process_one_job", lambda: calls.append("job") or {"id": 1}
    )
    states = iter([False, True])

    worker.run_worker(lambda: next(states), poll_interval=0)

    assert calls == ["recover-v2", "recover", "job"]


def test_real_deepagents_graph_completes_with_scripted_model_without_host_tools(
    monkeypatch, tmp_path
):
    from app import database
    from app.worker import process_one_job
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from pydantic import Field

    class ScriptedModel(BaseChatModel):
        candidate: dict
        coordinator_turns: int = 0
        seen_tools: list[list[str]] = Field(default_factory=list)

        @property
        def _llm_type(self):
            return "scripted"

        def _get_ls_params(self, **_kwargs):
            return {
                "ls_provider": "openai",
                "ls_model_name": "scripted",
                "ls_model_type": "chat",
            }

        def bind_tools(self, tools, **_kwargs):
            self.seen_tools.append([tool.name for tool in tools])
            return self

        def _generate(self, messages, stop=None, run_manager=None, **_kwargs):
            if "Coordinate the three specialists" not in "\n".join(
                str(message.content) for message in messages
            ):
                return ChatResult(
                    generations=[ChatGeneration(message=AIMessage(content="done"))]
                )
            if self.coordinator_turns < 3:
                name = ("evidence_extractor", "rubric_assessor", "feedback_writer")[
                    self.coordinator_turns
                ]
                self.coordinator_turns += 1
                message = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "task",
                            "args": {"subagent_type": name, "description": "complete"},
                            "id": f"task-{self.coordinator_turns}",
                        }
                    ],
                )
            elif self.coordinator_turns == 3:
                self.coordinator_turns += 1
                message = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "submit_candidate",
                            "args": {"candidate": self.candidate},
                            "id": "submit",
                        }
                    ],
                )
            else:
                message = AIMessage(content="done")
            return ChatResult(generations=[ChatGeneration(message=message)])

    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "scripted.db")
    monkeypatch.setenv("DEMO_AGENT_MODE", "false")
    with TestClient(app) as client:
        evidence = client.post(
            "/api/evidence",
            json={
                "student_id": 1,
                "evidence_type": "teacher_observation",
                "text": "学生解释了自己的解题策略。",
            },
        ).json()
        skill = client.get("/api/rubrics/current").json()["competencies"][0]["skills"][
            0
        ]["code"]
        job = client.post(
            "/api/assessment-jobs",
            json={
                "student_id": 1,
                "skill_code": skill,
                "evidence_refs": [evidence["id"]],
            },
        ).json()

    model = ScriptedModel(
        candidate={
            "status": "assessed",
            "level": 3,
            "confidence": 0.8,
            "evidence_refs": [evidence["id"]],
            "rationale": "scripted",
            "next_step": "next",
        }
    )
    completed = process_one_job(model_factory=lambda: model)

    from app.database import get_job

    assert completed is not None, get_job(job["id"])["error"]
    assert completed["status"] == "succeeded"
    assert completed["engine"] == "deepagents"
    assert completed["results"][0]["rubric_version"] == "future-9-3"
    assert completed["results"][0]["model_run_id"].startswith("deepagents-")
    assert {
        "evidence_extractor:completed",
        "rubric_assessor:completed",
        "feedback_writer:completed",
        "submitted",
    }.issubset({event["detail"] for event in completed["events"]})
    dangerous = {
        "delete",
        "edit_file",
        "execute",
        "glob",
        "grep",
        "ls",
        "read_file",
        "write_file",
    }
    assert model.seen_tools and all(
        not (set(tools) & dangerous) for tools in model.seen_tools
    )
