import json
import os
from io import BytesIO
from urllib.parse import parse_qs
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from .database import create_evidence as save_evidence
from .database import append_revision, create_job, current_rubric as load_current_rubric, get_job, initialize


RUBRIC = json.loads((Path(__file__).parent / "data" / "future_9.json").read_text(encoding="utf-8"))
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
        payload = {key: values[-1] for key, values in parse_qs((await request.body()).decode()).items()}
        uploaded = None
    try:
        student_id = int(payload["student_id"])
        evidence_type = payload["evidence_type"]
        text = payload.get("text", "")
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, "student_id, evidence_type, and text are required") from exc
    if evidence_type not in {"teacher_observation", "student_self_reflection", "student_work"}:
        raise HTTPException(422, "invalid evidence")
    filename = media_type = None
    content = None
    if uploaded:
        filename = uploaded.filename or ""
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(422, "unsupported evidence file")
        if suffix in {".jpg", ".jpeg", ".png"} and os.getenv("VISION_ENABLED", "false").lower() not in {"1", "true", "yes"}:
            raise HTTPException(422, "vision is disabled")
        content = await uploaded.read()
        if len(content) > MAX_EVIDENCE_BYTES:
            raise HTTPException(422, "evidence file exceeds 10MiB")
        media_type = uploaded.content_type
        if suffix in {".txt", ".md"} and not text:
            text = content.decode("utf-8", errors="replace")
        if suffix == ".pdf" and not text:
            from pypdf import PdfReader

            text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
    if not text.strip() and not content:
        raise HTTPException(422, "invalid evidence")
    try:
        return save_evidence(student_id, evidence_type, text, filename, media_type, content)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/assessment-jobs", status_code=201)
async def create_assessment_job(request: Request) -> dict:
    payload = await request.json()
    try:
        return create_job(int(payload["student_id"]), payload["skill_code"], payload["evidence_refs"])
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
                yield "event: status\ndata: " + json.dumps({"status": current["status"], "events": current["events"]}, ensure_ascii=False) + "\n\n"
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
