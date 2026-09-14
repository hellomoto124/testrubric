import os
import signal
import sqlite3
import time
import uuid

from .database import (
    append_v2_result,
    append_result,
    claim_next_v2_job,
    claim_next_job,
    fail_v2_job,
    fail_job,
    record_event,
    record_v2_event,
    recover_running_jobs_v2,
    recover_running_jobs,
    task_context,
    v2_task_context,
)


def process_one_job(agent_builder=None, model_factory=None):
    """A single process claims at most one queued job."""
    v2_job = claim_next_v2_job()
    if v2_job:
        return _process_v2_job(v2_job, agent_builder, model_factory)
    job = claim_next_job()
    if not job:
        return None
    return _process_legacy_job(job, agent_builder, model_factory)


def _demo_v2_judgments(job):
    judgments = []
    for group in job["config_snapshot"]["groups"]:
        value = 4 if group["level"] <= 3 else 2 if group["level"] == 4 else 0
        for indicator in group["indicators"]:
            judgments.append(
                {
                    "indicator_id": indicator["database_id"],
                    "observation_state": "observed",
                    "ordinal_score": value,
                    "evidence_refs": job["evidence_refs"],
                    "fragment_locator": "模拟证据全文",
                    "reason": "模拟测试数据的确定性指标判断",
                    "support_context": job["support_level"],
                }
            )
    return judgments


def _process_v2_job(job, agent_builder=None, model_factory=None):
    from .assessment_v2 import score as score_v2

    try:
        context = v2_task_context(job["id"])
        if os.getenv("DEMO_AGENT_MODE", "true").lower() in {"1", "true", "yes"}:
            record_v2_event(job["id"], "evidence_extractor", "completed:demo")
            judgments = _demo_v2_judgments(job)
            record_v2_event(job["id"], "rubric_assessor", "completed:demo")
            result = score_v2(
                job["config_snapshot"],
                judgments,
                job["target_snapshot"]["target_level"],
                set(job["evidence_refs"]),
            )
            record_v2_event(job["id"], "host_scoring", "anchor_interp_v1")
            feedback = "已形成模拟连续评分；下一步请结合新的课堂证据复核关键指标。"
            record_v2_event(job["id"], "feedback_writer", "completed:demo")
            return append_v2_result(
                job["id"],
                result
                | {
                    "judgments": judgments,
                    "feedback": feedback,
                    "rubric_code": job["rubric_code"],
                    "scoring_config_version": job["config_snapshot"]["version"],
                    "target_version": job["target_snapshot"]["target_version"],
                    "model_run_id": "demo-v2-" + str(job["id"]),
                },
                "demo_deterministic_v2",
            )

        from .agents import build_v2_deep_agent, configured_model

        extraction, host_result, feedback = [], {}, []

        def save_extraction(items):
            extraction[:] = items
            return {"accepted": True}

        def save_judgments(items):
            host_result.update(
                score_v2(
                    job["config_snapshot"],
                    items,
                    job["target_snapshot"]["target_level"],
                    set(job["evidence_refs"]),
                )
                | {"judgments": items}
            )
            return {"accepted": True, "host_scoring": "complete"}

        def load_host_result():
            if not host_result:
                raise RuntimeError("host score is not available")
            return host_result

        def save_feedback(text):
            feedback[:] = [text]
            return {"accepted": True}

        builder = agent_builder or build_v2_deep_agent
        agent = builder(
            (model_factory or configured_model)(),
            lambda: context | {"extracted_fragments": extraction},
            save_extraction,
            save_judgments,
            load_host_result,
            save_feedback,
        )
        required = ["evidence_extractor", "rubric_assessor", "feedback_writer"]
        completed = []
        dispatched = []
        task_types = {}
        for update in agent.stream(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Run the three required stages in order and submit each output.",
                    }
                ]
            },
            stream_mode="updates",
        ):
            for event in update.values():
                if not isinstance(event, dict):
                    continue
                for message in event.get("messages", []):
                    for call in getattr(message, "tool_calls", []):
                        name = call.get("args", {}).get("subagent_type")
                        if call.get("name") == "task" and call.get("id") and name in required:
                            if len(dispatched) >= len(required) or name != required[len(dispatched)]:
                                raise RuntimeError("V2 subagent dispatch order is invalid")
                            dispatched.append(name)
                            task_types[call["id"]] = name
                    call_id = getattr(message, "tool_call_id", None)
                    if getattr(message, "name", None) == "task" and call_id in task_types:
                        name = task_types[call_id]
                        if getattr(message, "status", "success") == "error":
                            raise RuntimeError(name + " failed")
                        if name != required[len(completed)]:
                            raise RuntimeError("V2 subagents completed out of order")
                        completed.append(name)
                        record_v2_event(job["id"], name, "completed:" + call_id)
                        if name == "rubric_assessor":
                            if not host_result:
                                raise RuntimeError("rubric assessor did not submit judgments")
                            record_v2_event(job["id"], "host_scoring", "anchor_interp_v1")
        if dispatched != required or completed != required or not extraction or not host_result or not feedback:
            raise RuntimeError("Deep Agents did not complete the V2 assessment contract")
        return append_v2_result(
            job["id"],
            host_result
            | {
                "feedback": feedback[0],
                "rubric_code": job["rubric_code"],
                "scoring_config_version": job["config_snapshot"]["version"],
                "target_version": job["target_snapshot"]["target_version"],
                "model_run_id": "deepagents-v2-" + str(uuid.uuid4()),
            },
            "deepagents_v2",
        )
    except Exception as exc:  # noqa: BLE001 - failed jobs are retried
        fail_v2_job(job["id"], str(exc))
        return None


def _process_legacy_job(job, agent_builder=None, model_factory=None):
    try:
        context = task_context(job["id"])
        if os.getenv("DEMO_AGENT_MODE", "true").lower() in {"1", "true", "yes"}:
            text = " ".join(item["text"] for item in context["evidence"])
            result = {
                "status": "assessed"
                if len(text.strip()) >= 12
                else "insufficient_evidence",
                "level": 3 if len(text.strip()) >= 12 else None,
                "confidence": 0.6 if len(text.strip()) >= 12 else 0.0,
                "evidence_refs": job["evidence_refs"],
                "rationale": "demo deterministic assessment"
                if len(text.strip()) >= 12
                else "insufficient evidence",
                "next_step": "collect one concrete example"
                if len(text.strip()) < 12
                else "ask for a second example",
                "rubric_version": context["rubric"]["rubric_version"],
                "model_run_id": "demo-" + str(job["id"]),
            }
            return append_result(job["id"], result, "demo_deterministic")
        from .agents import build_deep_agent, configured_model

        required, seen, submitted, task_types = (
            {"evidence_extractor", "rubric_assessor", "feedback_writer"},
            set(),
            [],
            {},
        )
        run_id = "deepagents-" + str(uuid.uuid4())

        def submit(result):
            submitted.append(
                result
                | {
                    "rubric_version": context["rubric"]["rubric_version"],
                    "model_run_id": run_id,
                }
            )
            return {"accepted": True}

        agent = (agent_builder or build_deep_agent)(
            (model_factory or configured_model)(), lambda: context, submit
        )
        for update in agent.stream(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Use evidence_extractor, rubric_assessor, then feedback_writer; submit exactly one candidate.",
                    }
                ]
            },
            stream_mode="updates",
        ):
            for event in update.values():
                if not isinstance(event, dict):
                    continue
                for message in event.get("messages", []):
                    for call in getattr(message, "tool_calls", []):
                        if (
                            call["name"] == "task"
                            and call.get("id")
                            and call["args"].get("subagent_type") in required
                        ):
                            task_types[call["id"]] = call["args"]["subagent_type"]
                    if (
                        getattr(message, "name", None) == "task"
                        and getattr(message, "tool_call_id", None) in task_types
                    ):
                        name = task_types[message.tool_call_id]
                        if getattr(message, "status", "success") == "error":
                            record_event(job["id"], "subagent", name + ":failed")
                        else:
                            seen.add(name)
                            record_event(job["id"], "subagent", name + ":completed")
        if seen != required or not submitted:
            raise RuntimeError(
                "Deep Agents did not complete required subagents and candidate submission"
            )
        record_event(job["id"], "candidate", "submitted")
        return append_result(job["id"], submitted[-1], "deepagents")
    except Exception as exc:  # noqa: BLE001 - failed jobs are retried
        fail_job(job["id"], str(exc))
        return None


def run_worker(should_stop, poll_interval=0.1):
    recover_running_jobs_v2()
    recover_running_jobs()
    next_heartbeat = 0.0
    while not should_stop():
        if time.monotonic() >= next_heartbeat:
            try:
                from .admin_v2 import record_worker_heartbeat

                record_worker_heartbeat()
            except sqlite3.OperationalError:
                pass
            next_heartbeat = time.monotonic() + 5
        process_one_job()
        if should_stop():
            return
        time.sleep(poll_interval)


def main():
    stopping = False

    def stop(*_args):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    run_worker(lambda: stopping)


if __name__ == "__main__":
    main()
