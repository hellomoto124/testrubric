import json
import os
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from .database import (
    append_revision,
    class_dashboard,
    create_job,
    demo_context,
    get_job,
    initialize,
    school_dashboard,
    student_profile,
)
from .database import create_evidence as save_evidence
from .database import current_rubric as load_current_rubric
from .database import append_v2_revision, create_v2_job, get_v2_job, v2_history
from .assessment_v2 import score as score_v2
from .rubric_v2 import (
    V2Conflict,
    V2Invalid,
    V2NotFound,
    create_draft,
    create_target,
    get_config,
    get_published_config,
    list_targets,
    publish_config,
    update_config,
)

RUBRIC = json.loads(
    (Path(__file__).parent / "data" / "future_9.json").read_text(encoding="utf-8")
)
MAX_EVIDENCE_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".jpg", ".jpeg", ".png"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize(RUBRIC)
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/api/rubrics/current")
def current_rubric() -> dict:
    return load_current_rubric()


@app.get("/api/v2/rubrics/current")
def current_rubric_v2() -> dict:
    from .database import v2_catalog

    return v2_catalog()


def v2_result(operation):
    try:
        return operation()
    except V2NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except V2Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except V2Invalid as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v2/skills/{code}/scoring-rubric")
def scoring_rubric_v2(code: str) -> dict:
    return v2_result(lambda: get_published_config(code))


@app.get("/api/v2/scoring-rubrics/{config_id}")
def scoring_rubric_detail_v2(config_id: int) -> dict:
    return v2_result(lambda: get_config(config_id))


@app.post("/api/v2/scoring-rubrics/drafts", status_code=201)
async def create_scoring_draft(request: Request) -> dict:
    payload = await request.json()
    if set(payload) != {"skill_code"}:
        raise HTTPException(422, "only skill_code is allowed")
    return v2_result(lambda: create_draft(payload["skill_code"]))


@app.patch("/api/v2/scoring-rubrics/{config_id}")
async def update_scoring_rubric_v2(config_id: int, request: Request) -> dict:
    payload = await request.json()
    return v2_result(lambda: update_config(config_id, payload))


@app.post("/api/v2/scoring-rubrics/{config_id}/publish")
def publish_v2(config_id: int):
    return v2_result(lambda: publish_config(config_id))


@app.post("/api/v2/assessment-jobs", status_code=201)
async def create_assessment_job_v2(request: Request) -> dict:
    payload = await request.json()
    required = {"student_id", "skill_code", "evidence_refs", "idempotency_key"}
    allowed = required | {"context", "support_level", "period"}
    if (
        not required <= set(payload)
        or not set(payload) <= allowed
        or not isinstance(payload["idempotency_key"], str)
        or not payload["idempotency_key"].strip()
    ):
        raise HTTPException(422, "only V2 assessment job fields are allowed")
    try:
        return create_v2_job(
            payload["student_id"],
            payload["skill_code"],
            payload["evidence_refs"],
            get_published_config(payload["skill_code"]),
            payload.get("context", "未说明"),
            payload.get("support_level", "未说明"),
            payload.get("period", "default"),
            payload["idempotency_key"],
        )
    except (ValueError, V2NotFound) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v2/assessment-jobs/{job_id}")
def get_assessment_job_v2(job_id: int) -> dict:
    job = get_v2_job(job_id)
    if not job:
        raise HTTPException(404, "job does not exist")
    return job


@app.get("/api/v2/assessment-jobs/{job_id}/events")
async def assessment_events_v2(job_id: int):
    if not get_v2_job(job_id):
        raise HTTPException(404, "job does not exist")

    async def stream():
        last = None
        while True:
            current = get_v2_job(job_id)
            state = (current["status"], len(current["events"]))
            if state != last:
                yield (
                    "event: status\ndata: "
                    + json.dumps(
                        {"status": current["status"], "events": current["events"]},
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
                last = state
            if current["status"] in {"succeeded", "failed"}:
                return
            import asyncio

            await asyncio.sleep(0.1)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/v2/assessments/{result_id}/revisions", status_code=201)
async def revise_assessment_v2(result_id: int, request: Request) -> dict:
    payload = await request.json()
    if set(payload) != {"judgments", "reason"} or not isinstance(payload["judgments"], list) or not isinstance(payload["reason"], str) or not payload["reason"].strip():
        raise HTTPException(422, "judgments and reason are required")
    from .database import connect

    with connect() as connection:
        row = connection.execute(
            "SELECT job_id, result FROM assessment_results_v2 WHERE id = ?",
            (result_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "assessment result does not exist")
    job = get_v2_job(row[0])
    original = json.loads(row[1])
    original_ids = {item["indicator_id"] for item in original.get("judgments", [])}
    revised_ids = {item.get("indicator_id") for item in payload["judgments"]}
    if revised_ids != original_ids or len(revised_ids) != len(payload["judgments"]):
        raise HTTPException(422, "revisions must contain exactly the original indicators")
    try:
        result = score_v2(
            job["config_snapshot"],
            payload["judgments"],
            job["target_snapshot"]["target_level"],
            set(job["evidence_refs"]),
        ) | {
            "judgments": payload["judgments"],
            "feedback": original.get("feedback", "教师已完成人工复核。"),
            "rubric_code": job["rubric_code"],
            "scoring_config_version": job["config_snapshot"]["version"],
            "target_version": job["target_snapshot"]["target_version"],
        }
        return append_v2_revision(result_id, result, payload["reason"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v2/students/{student_id}/skills/{skill_code}/history")
def assessment_history_v2(student_id: int, skill_code: str) -> dict:
    return v2_history(student_id, skill_code)


@app.get("/api/v2/dashboard/{scope}/{subject_id}")
def dashboard_v2(scope: str, subject_id: int, skill_code: str | None = None) -> dict:
    from .dashboard_v2 import dashboard

    result = dashboard(scope, subject_id, skill_code)
    if not result:
        raise HTTPException(404, "dashboard scope or subject does not exist")
    return result


@app.get("/api/v2/targets")
def targets_v2(grade: str | None = None, term: str | None = None, skill_code: str | None = None):
    return list_targets(grade, term, skill_code)


@app.put("/api/v2/targets/{grade}/{term}/{skill_code}", status_code=201)
async def create_target_v2(grade: str, term: str, skill_code: str, request: Request):
    payload = await request.json()
    if set(payload) != {"target_level", "target_version"}:
        raise HTTPException(422, "target_level and target_version are required")
    return v2_result(
        lambda: create_target(
            grade,
            term,
            skill_code,
            payload["target_level"],
            payload["target_version"],
        )
    )


@app.get("/api/dashboard/school")
def get_school_dashboard() -> dict:
    dashboard = school_dashboard()
    if not dashboard:
        raise HTTPException(404, "school does not exist")
    return dashboard


@app.get("/api/classes/{class_id}/dashboard")
def get_class_dashboard(class_id: int) -> dict:
    dashboard = class_dashboard(class_id)
    if not dashboard:
        raise HTTPException(404, "class does not exist")
    return dashboard


@app.get("/api/students/{student_id}/profile")
def get_student_profile(student_id: int) -> dict:
    profile = student_profile(student_id)
    if not profile:
        raise HTTPException(404, "student does not exist")
    return profile


@app.get("/api/demo/context")
def get_demo_context() -> dict:
    return demo_context()


@app.post("/api/evidence", status_code=201)
async def create_evidence(request: Request) -> dict:
    if request.headers.get("content-type", "").startswith("application/json"):
        payload = await request.json()
        uploaded = None
    elif request.headers.get("content-type", "").startswith("multipart/form-data"):
        form = await request.form()
        payload = dict(form)
        uploaded = form.get("file")
    else:
        payload = {
            key: values[-1]
            for key, values in parse_qs((await request.body()).decode()).items()
        }
        uploaded = None
    try:
        student_id = int(payload["student_id"])
        evidence_type = payload["evidence_type"]
        text = payload.get("text", "")
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            422, "student_id, evidence_type, and text are required"
        ) from exc
    if evidence_type not in {
        "teacher_observation",
        "student_self_reflection",
        "student_work",
    }:
        raise HTTPException(422, "invalid evidence")
    filename = media_type = None
    content = None
    if uploaded:
        filename = uploaded.filename or ""
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(422, "unsupported evidence file")
        if suffix in {".jpg", ".jpeg", ".png"} and os.getenv(
            "VISION_ENABLED", "false"
        ).lower() not in {"1", "true", "yes"}:
            raise HTTPException(422, "vision is disabled")
        content = await uploaded.read()
        if len(content) > MAX_EVIDENCE_BYTES:
            raise HTTPException(422, "evidence file exceeds 10MiB")
        media_type = uploaded.content_type
        if suffix in {".txt", ".md"} and not text:
            text = content.decode("utf-8", errors="replace")
        if suffix == ".pdf" and not text:
            from pypdf import PdfReader
            from pypdf.errors import FileNotDecryptedError, PdfReadError, PdfStreamError

            try:
                text = "\n".join(
                    page.extract_text() or ""
                    for page in PdfReader(BytesIO(content)).pages
                )
            except (FileNotDecryptedError, PdfReadError, PdfStreamError) as exc:
                raise HTTPException(422, "PDF cannot be read") from exc
            if not text.strip():
                raise HTTPException(422, "PDF has no extractable text")
    if not text.strip() and not content:
        raise HTTPException(422, "invalid evidence")
    try:
        return save_evidence(
            student_id, evidence_type, text, filename, media_type, content
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/assessment-jobs", status_code=201)
async def create_assessment_job(request: Request) -> dict:
    payload = await request.json()
    try:
        return create_job(
            int(payload["student_id"]), payload["skill_code"], payload["evidence_refs"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/assessment-jobs/{job_id}")
def get_assessment_job(job_id: int) -> dict:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "job does not exist")
    return job


@app.get("/api/assessment-jobs/{job_id}/events")
async def assessment_events(job_id: int):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "job does not exist")

    async def stream():
        last = None
        while True:
            current = get_job(job_id)
            state = (current["status"], len(current["events"]))
            if state != last:
                yield (
                    "event: status\ndata: "
                    + json.dumps(
                        {"status": current["status"], "events": current["events"]},
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
                last = state
            if current["status"] in {"succeeded", "failed"}:
                return
            import asyncio

            await asyncio.sleep(0.1)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.patch("/api/assessments/{assessment_result_id}")
async def revise_assessment(assessment_result_id: int, request: Request) -> dict:
    try:
        return append_revision(assessment_result_id, await request.json())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
