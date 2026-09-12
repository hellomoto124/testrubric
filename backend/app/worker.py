import os
import time

from .database import append_result, claim_next_job, fail_job, get_job, record_event, recover_running_jobs, task_context


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

        seen, submitted = set(), []
        agent = (agent_builder or build_deep_agent)((model_factory or configured_model)(), lambda: context, lambda result: submitted.append(result) or append_result(job["id"], result, "deepagents"))
        for update in agent.stream({"messages": [{"role": "user", "content": "Use evidence_extractor, rubric_assessor, then feedback_writer; submit exactly one candidate."}]}, stream_mode="updates"):
            for name in set(update) & {"evidence_extractor", "rubric_assessor", "feedback_writer"}:
                seen.add(name)
                record_event(job["id"], "subagent", name)
        if seen != {"evidence_extractor", "rubric_assessor", "feedback_writer"} or not submitted:
            raise RuntimeError("Deep Agents did not complete required subagents and candidate submission")
        record_event(job["id"], "candidate", "submitted")
        return get_job(job["id"])
    except Exception as exc:
        fail_job(job["id"], str(exc))
        return None


def main():
    recover_running_jobs()
    while True:
        process_one_job()
        time.sleep(0.1)


if __name__ == "__main__":
    main()
