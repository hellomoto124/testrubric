import os
import uuid

from .database import append_result, claim_next_job, fail_job, get_job, task_context


def process_one_job():
    """A single process claims at most one queued job."""
    job = claim_next_job()
    if not job:
        return None
    try:
        context = task_context(job["id"])
        if os.getenv("DEMO_AGENT_MODE", "true").lower() in {"1", "true", "yes"}:
            text = " ".join(item["text"] for item in context["evidence"])
            result = {
                "status": "completed" if len(text.strip()) >= 12 else "insufficient_evidence",
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

        agent = build_deep_agent(configured_model(), lambda: context, lambda result: append_result(job["id"], result, "deepagents"))
        agent.invoke({"messages": [{"role": "user", "content": "Assess the current task and submit exactly one candidate."}]})
        return get_job(job["id"])
    except Exception as exc:
        fail_job(job["id"], str(exc))
        return None
