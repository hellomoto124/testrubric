import os
import signal
import time
import uuid

from .database import (
    append_result,
    claim_next_job,
    fail_job,
    record_event,
    recover_running_jobs,
    task_context,
)


def process_one_job(agent_builder=None, model_factory=None):
    """A single process claims at most one queued job."""
    job = claim_next_job()
    if not job:
        return None
    try:
        context = task_context(job["id"])
        if os.getenv("DEMO_AGENT_MODE", "true").lower() in {"1", "true", "yes"}:
            text = " ".join(item["text"] for item in context["evidence"])
            result = {
                "status": "assessed" if len(text.strip()) >= 12 else "insufficient_evidence",
                "level": 3 if len(text.strip()) >= 12 else None,
                "confidence": 0.6 if len(text.strip()) >= 12 else 0.0,
                "evidence_refs": job["evidence_refs"],
                "rationale": "demo deterministic assessment" if len(text.strip()) >= 12 else "insufficient evidence",
                "next_step": "collect one concrete example" if len(text.strip()) < 12 else "ask for a second example",
                "rubric_version": context["rubric"]["rubric_version"],
                "model_run_id": "demo-" + str(job["id"]),
            }
            return append_result(job["id"], result, "demo_deterministic")
        from .agents import build_deep_agent, configured_model

        required, seen, submitted, task_types = {"evidence_extractor", "rubric_assessor", "feedback_writer"}, set(), [], {}
        run_id = "deepagents-" + str(uuid.uuid4())

        def submit(result):
            submitted.append(result | {"rubric_version": context["rubric"]["rubric_version"], "model_run_id": run_id})
            return {"accepted": True}

        agent = (agent_builder or build_deep_agent)((model_factory or configured_model)(), lambda: context, submit)
        for update in agent.stream({"messages": [{"role": "user", "content": "Use evidence_extractor, rubric_assessor, then feedback_writer; submit exactly one candidate."}]}, stream_mode="updates"):
            for event in update.values():
                if not isinstance(event, dict):
                    continue
                for message in event.get("messages", []):
                    for call in getattr(message, "tool_calls", []):
                        if call["name"] == "task" and call.get("id") and call["args"].get("subagent_type") in required:
                            task_types[call["id"]] = call["args"]["subagent_type"]
                    if getattr(message, "name", None) == "task" and getattr(message, "tool_call_id", None) in task_types:
                        name = task_types[message.tool_call_id]
                        seen.add(name)
                        record_event(job["id"], "subagent", name + ":completed")
        if seen != required or not submitted:
            raise RuntimeError("Deep Agents did not complete required subagents and candidate submission")
        record_event(job["id"], "candidate", "submitted")
        return append_result(job["id"], submitted[-1], "deepagents")
    except Exception as exc:  # noqa: BLE001 - failed jobs are retried
        fail_job(job["id"], str(exc))
        return None


def run_worker(should_stop, poll_interval=0.1):
    recover_running_jobs()
    while not should_stop():
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
