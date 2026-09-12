"""Restricted Deep Agents coordinator for one assessment task."""

import os

from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.profiles import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    register_harness_profile,
)
from langchain_core.tools import tool


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
    def submit_candidate(candidate: dict) -> dict:
        """Submit one candidate assessment result for validation."""
        return candidate_sink(candidate)

    tools = [read_current_task, submit_candidate]
    register_harness_profile(
        "openai",
        HarnessProfile(
            excluded_tools=frozenset({"delete", "edit_file", "execute", "glob", "grep", "ls", "read_file", "write_file"}),
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        ),
    )
    subagents = [
        {"name": name, "description": description, "system_prompt": "Use only the supplied tools. Return concise assessment work.", "tools": tools}
        for name, description in (
            ("evidence_extractor", "Extract relevant evidence from the current task."),
            ("rubric_assessor", "Assess evidence against the supplied rubric."),
            ("feedback_writer", "Write concise, actionable feedback from the assessment."),
        )
    ]
    return creator(
        model=model,
        tools=tools,
        subagents=subagents,
        system_prompt="Coordinate the three specialists. Never access files, SQL, or anything outside the provided tools.",
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
