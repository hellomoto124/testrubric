"""Restricted Deep Agents coordinator for one assessment task."""

import os
from typing import Literal

from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.profiles import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    register_harness_profile,
)
from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field, StrictInt


class AssessmentCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["assessed", "insufficient_evidence"]
    level: StrictInt | None
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[StrictInt]
    rationale: str = Field(min_length=1)
    next_step: str = Field(min_length=1)


class EvidenceFragment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_ref: StrictInt
    behavior: str = Field(min_length=1)
    context: str = Field(min_length=1)
    support_level: str = Field(min_length=1)
    opportunity: str = Field(min_length=1)


class IndicatorJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    indicator_id: StrictInt
    observation_state: Literal["observed", "unknown", "unrelated", "conflict"]
    ordinal_score: StrictInt | None
    evidence_refs: list[StrictInt]
    fragment_locator: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    support_context: str = Field(min_length=1)


class ChineseFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback: str = Field(min_length=1)


def build_deep_agent(model, task_loader, candidate_sink, creator=None):
    """Build an agent that can see only its current task and submit a candidate."""
    if creator is None:
        from deepagents import create_deep_agent

        creator = create_deep_agent

    @tool
    def read_current_task() -> dict:
        """Read only the current task's evidence and rubric."""
        return task_loader()

    @tool
    def submit_candidate(candidate: AssessmentCandidate) -> dict:
        """Submit only status, level, confidence, evidence_refs, rationale, and next_step."""
        return candidate_sink(candidate.model_dump())

    tools = [read_current_task, submit_candidate]
    register_harness_profile(
        "openai",
        HarnessProfile(
            excluded_tools=frozenset(
                {
                    "delete",
                    "edit_file",
                    "execute",
                    "glob",
                    "grep",
                    "ls",
                    "read_file",
                    "write_file",
                }
            ),
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        ),
    )
    subagents = [
        {
            "name": name,
            "description": description,
            "system_prompt": "Use only the supplied tools. Submit candidates only through the submit_candidate schema; never invent rubric_version or model_run_id.",
            "tools": tools,
        }
        for name, description in (
            ("evidence_extractor", "Extract relevant evidence from the current task."),
            ("rubric_assessor", "Assess evidence against the supplied rubric."),
            (
                "feedback_writer",
                "Write concise, actionable feedback from the assessment.",
            ),
        )
    ]
    return creator(
        model=model,
        tools=tools,
        subagents=subagents,
        system_prompt="Coordinate the three specialists. Never access files, SQL, or anything outside the provided tools. Submit candidates only through submit_candidate with its schema; never invent rubric_version or model_run_id.",
        middleware=[FilesystemMiddleware(tools=["read_file"])],
    )


def build_v2_deep_agent(
    model,
    task_loader,
    extraction_sink,
    judgment_sink,
    host_result_loader,
    feedback_sink,
    creator=None,
):
    """Build one restricted coordinator for the ordered V2 assessment stages."""
    if creator is None:
        from deepagents import create_deep_agent

        creator = create_deep_agent

    @tool
    def read_current_task() -> dict:
        """Read only this job's evidence, context, target and rubric snapshot."""
        return task_loader()

    @tool
    def submit_extraction(fragments: list[EvidenceFragment]) -> dict:
        """Submit extracted behavior fragments without scores."""
        return extraction_sink([item.model_dump() for item in fragments])

    @tool
    def submit_judgments(judgments: list[IndicatorJudgment]) -> dict:
        """Submit indicator observations only; the host computes every score."""
        return judgment_sink([item.model_dump() for item in judgments])

    @tool
    def read_host_result() -> dict:
        """Read the immutable host-computed score before writing feedback."""
        return host_result_loader()

    @tool
    def submit_feedback(feedback: ChineseFeedback) -> dict:
        """Submit Chinese feedback without score fields."""
        return feedback_sink(feedback.feedback)

    tools = [
        read_current_task,
        submit_extraction,
        submit_judgments,
        read_host_result,
        submit_feedback,
    ]
    stage_tools = {
        "evidence_extractor": [read_current_task, submit_extraction],
        "rubric_assessor": [read_current_task, submit_judgments],
        "feedback_writer": [read_current_task, read_host_result, submit_feedback],
    }
    prompts = {
        "evidence_extractor": "Extract behavior, context, help level and opportunity. Do not score.",
        "rubric_assessor": "Use extracted evidence and submit indicator judgments only. Never submit weights, totals, levels, targets or versions.",
        "feedback_writer": "Read the host result, then write concise Chinese feedback. Never change a score.",
    }
    subagents = [
        {
            "name": name,
            "description": prompts[name],
            "system_prompt": prompts[name] + " Use only supplied tools.",
            "tools": stage_tools[name],
        }
        for name in ("evidence_extractor", "rubric_assessor", "feedback_writer")
    ]
    return creator(
        model=model,
        tools=tools,
        subagents=subagents,
        system_prompt=(
            "Dispatch evidence_extractor, then rubric_assessor, then feedback_writer. "
            "Each must finish successfully. Use only supplied tools; never access files or SQL."
        ),
        middleware=[FilesystemMiddleware(tools=["read_file"])],
    )


def configured_model():
    """Use OpenAI-compatible settings only when real-agent mode is enabled."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=os.environ["OPENAI_COMPATIBLE_MODEL"],
        api_key=os.environ["OPENAI_COMPATIBLE_API_KEY"],
        base_url=os.environ["OPENAI_COMPATIBLE_BASE_URL"],
    )
