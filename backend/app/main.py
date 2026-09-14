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


@app.get("/api/v2/skills/{code}/scoring-rubric")
def scoring_rubric_v2(code: str) -> dict:
    from .database import connect

    with connect() as c:
        row = c.execute(
            "SELECT id FROM scoring_configs_v2 WHERE code = ? AND status = 'published'",
            (code + ".demo",),
        ).fetchone()
        if not row:
            raise HTTPException(404, "published scoring rubric not found")
        groups = []
        for group_id, level, group_code in c.execute(
            "SELECT id, level, code FROM indicator_groups_v2 WHERE config_id = ? ORDER BY level",
            row,
        ):
            indicators = [
                dict(zip(("id", "weight"), item))
                for item in c.execute(
                    "SELECT code, weight FROM indicators_v2 WHERE group_id = ?",
                    (group_id,),
                )
            ]
            groups.append({"id": group_code, "level": level, "indicators": indicators})
    return {"code": code, "groups": groups}


@app.post("/api/v2/scoring-rubrics/drafts", status_code=201)
async def create_scoring_draft(request: Request) -> dict:
    payload = await request.json()
    if set(payload) != {"skill_code"}:
        raise HTTPException(422, "only skill_code is allowed")
    from .database import connect

    with connect() as c:
        row = c.execute(
            "SELECT rubric_id FROM scoring_configs_v2 WHERE code=? AND status='published'",
            (payload["skill_code"] + ".demo",),
        ).fetchone()
        if not row:
            raise HTTPException(404, "published rubric not found")
        config_id = c.execute(
            "INSERT INTO scoring_configs_v2 (rubric_id,code,status,calibration_status,is_simulated_test_data) VALUES (?,?,'draft','uncalibrated',1)",
            (row[0], payload["skill_code"] + ".draft"),
        ).lastrowid
    return {"id": config_id, "status": "draft"}


@app.post("/api/v2/scoring-rubrics/{config_id}/publish")
def publish_v2(config_id: int):
    from .database import connect

    with connect() as c:
        status = c.execute(
            "SELECT status FROM scoring_configs_v2 WHERE id=?", (config_id,)
        ).fetchone()
        if not status:
            raise HTTPException(404, "config not found")
        if status[0] != "reviewed":
            raise HTTPException(409, "config must be reviewed")
        c.execute(
            "UPDATE scoring_configs_v2 SET status='published' WHERE id=?", (config_id,)
        )
    return {"id": config_id, "status": "published"}


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
