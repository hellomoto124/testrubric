import sqlite3
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Optional


DATABASE_PATH = Path(__file__).parent / "data" / "app.db"


@contextmanager
def connect():
    connection = sqlite3.connect(DATABASE_PATH)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize(rubric: dict) -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schools (id INTEGER PRIMARY KEY, name TEXT NOT NULL, is_simulated_test_data INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS classes (id INTEGER PRIMARY KEY, school_id INTEGER NOT NULL, name TEXT NOT NULL, is_simulated_test_data INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL, anonymous_id TEXT NOT NULL, is_simulated_test_data INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS rubrics (id INTEGER PRIMARY KEY, rubric_version TEXT NOT NULL, source_url TEXT NOT NULL, license_note TEXT NOT NULL, local_adaptation TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS competencies (id INTEGER PRIMARY KEY, rubric_id INTEGER NOT NULL, position INTEGER NOT NULL, name TEXT NOT NULL, description TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS skills (id INTEGER PRIMARY KEY, competency_id INTEGER NOT NULL, position INTEGER NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS levels (id INTEGER PRIMARY KEY, skill_id INTEGER NOT NULL, level INTEGER NOT NULL, descriptors TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS evidence (id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL, evidence_type TEXT NOT NULL, text TEXT NOT NULL, filename TEXT, media_type TEXT, content BLOB, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS assessment_jobs (id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL, skill_code TEXT NOT NULL, evidence_refs TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0, engine TEXT, error TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS assessment_results (id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, revision INTEGER NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(job_id, revision));
            CREATE TABLE IF NOT EXISTS job_events (id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, stage TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            """
        )
        try:
            connection.execute("ALTER TABLE assessment_jobs ADD COLUMN status_detail TEXT")
        except sqlite3.OperationalError:
            pass
        if connection.execute("SELECT count(*) FROM schools").fetchone()[0]:
            return
        connection.execute("INSERT INTO schools VALUES (1, ?, 1)", ("模拟测试学校",))
        connection.executemany("INSERT INTO classes VALUES (?, 1, ?, 1)", [(number, f"模拟测试班级{number}") for number in range(1, 4)])
        connection.executemany(
            "INSERT INTO students VALUES (?, ?, ?, 1)",
            [(number, 1 if number <= 7 else 2 if number <= 14 else 3, f"模拟学生{number:02d}") for number in range(1, 21)],
        )
        rubric_id = connection.execute(
            "INSERT INTO rubrics (rubric_version, source_url, license_note, local_adaptation) VALUES (?, ?, ?, ?)",
            (rubric["rubric_version"], rubric["source_url"], rubric["license_note"], rubric["local_adaptation"]),
        ).lastrowid
        for competency_position, competency in enumerate(rubric["competencies"]):
            competency_id = connection.execute(
                "INSERT INTO competencies (rubric_id, position, name, description) VALUES (?, ?, ?, ?)",
                (rubric_id, competency_position, competency["name"], competency["description"]),
            ).lastrowid
            for skill_position, skill in enumerate(competency["skills"]):
                skill_id = connection.execute(
                    "INSERT INTO skills (competency_id, position, code, name) VALUES (?, ?, ?, ?)",
                    (competency_id, skill_position, skill["code"], skill["name"]),
                ).lastrowid
                connection.executemany(
                    "INSERT INTO levels (skill_id, level, descriptors) VALUES (?, ?, ?)",
                    [(skill_id, level["level"], json.dumps(level["descriptors"], ensure_ascii=False)) for level in skill["levels"]],
                )


def current_rubric() -> dict:
    with connect() as connection:
        rubric = connection.execute("SELECT rubric_version, source_url, license_note, local_adaptation FROM rubrics").fetchone()
        competencies = []
        for competency_id, name, description in connection.execute("SELECT id, name, description FROM competencies ORDER BY position"):
            skills = []
            for skill_id, code, skill_name in connection.execute("SELECT id, code, name FROM skills WHERE competency_id = ? ORDER BY position", (competency_id,)):
                levels = [{"level": level, "descriptors": json.loads(descriptors)} for level, descriptors in connection.execute("SELECT level, descriptors FROM levels WHERE skill_id = ? ORDER BY level", (skill_id,))]
                skills.append({"code": code, "name": skill_name, "levels": levels})
            competencies.append({"name": name, "description": description, "skills": skills})
    return dict(zip(("rubric_version", "source_url", "license_note", "local_adaptation"), rubric)) | {"competencies": competencies}


def create_evidence(student_id: int, evidence_type: str, text: str, filename: Optional[str] = None, media_type: Optional[str] = None, content: Optional[bytes] = None) -> dict:
    with connect() as connection:
        if not connection.execute("SELECT 1 FROM students WHERE id = ?", (student_id,)).fetchone():
            raise ValueError("student does not exist")
        evidence_id = connection.execute(
            "INSERT INTO evidence (student_id, evidence_type, text, filename, media_type, content) VALUES (?, ?, ?, ?, ?, ?)",
            (student_id, evidence_type, text, filename, media_type, content),
        ).lastrowid
        row = connection.execute(
            "SELECT id, student_id, evidence_type, text, filename, media_type FROM evidence WHERE id = ?", (evidence_id,)
        ).fetchone()
    return dict(zip(("id", "student_id", "evidence_type", "text", "filename", "media_type"), row))


def create_job(student_id: int, skill_code: str, evidence_refs: list) -> dict:
    with connect() as connection:
        if not connection.execute("SELECT 1 FROM students WHERE id = ?", (student_id,)).fetchone() or not connection.execute("SELECT 1 FROM skills WHERE code = ?", (skill_code,)).fetchone():
            raise ValueError("student or skill does not exist")
        marks = ",".join("?" for _ in evidence_refs)
        if not evidence_refs or connection.execute("SELECT count(*) FROM evidence WHERE student_id = ? AND id IN (" + marks + ")", [student_id] + evidence_refs).fetchone()[0] != len(set(evidence_refs)):
            raise ValueError("evidence refs do not exist for student")
        job_id = connection.execute("INSERT INTO assessment_jobs (student_id, skill_code, evidence_refs) VALUES (?, ?, ?)", (student_id, skill_code, json.dumps(evidence_refs))).lastrowid
    return get_job(job_id)


def get_job(job_id: int) -> Optional[dict]:
    with connect() as connection:
        row = connection.execute("SELECT id, student_id, skill_code, evidence_refs, status, attempts, engine, error FROM assessment_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return None
        results = [dict(json.loads(result), id=result_id, revision=revision) for result_id, revision, result in connection.execute("SELECT id, revision, result FROM assessment_results WHERE job_id = ? ORDER BY revision", (job_id,))]
        events = [dict(zip(("id", "stage", "detail"), event)) for event in connection.execute("SELECT id, stage, detail FROM job_events WHERE job_id = ? ORDER BY id", (job_id,))]
    job = dict(zip(("id", "student_id", "skill_code", "evidence_refs", "status", "attempts", "engine", "error"), row))
    job["evidence_refs"] = json.loads(job["evidence_refs"])
    job["results"] = results
    job["events"] = events
    return job


def append_result(job_id: int, result: dict, engine: str) -> dict:
    with connect() as connection:
        row = connection.execute("SELECT student_id FROM assessment_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise ValueError("job does not exist")
        _validate_result(connection, row[0], result)
        revision = connection.execute("SELECT count(*) FROM assessment_results WHERE job_id = ?", (job_id,)).fetchone()[0] + 1
        connection.execute("INSERT INTO assessment_results (job_id, revision, result) VALUES (?, ?, ?)", (job_id, revision, json.dumps(result, ensure_ascii=False)))
        connection.execute("UPDATE assessment_jobs SET status = 'succeeded', engine = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (engine, job_id))
        connection.execute("INSERT INTO job_events (job_id, stage, detail) VALUES (?, ?, ?)", (job_id, "succeeded", engine))
    return get_job(job_id)


def _validate_result(connection, student_id: int, result: dict) -> None:
    required = {"status", "level", "confidence", "evidence_refs", "rationale", "next_step", "rubric_version", "model_run_id"}
    if not required.issubset(result) or result["status"] not in {"assessed", "insufficient_evidence"} or not isinstance(result["confidence"], (int, float)) or isinstance(result["confidence"], bool) or not 0 <= result["confidence"] <= 1 or not isinstance(result["evidence_refs"], list) or not result["evidence_refs"] or len(set(result["evidence_refs"])) != len(result["evidence_refs"]) or not result["rationale"] or not result["next_step"] or not result["model_run_id"]:
        raise ValueError("invalid assessment result")
    version = connection.execute("SELECT rubric_version FROM rubrics").fetchone()[0]
    if result["rubric_version"] != version:
        raise ValueError("invalid rubric version")
    if result["status"] == "assessed" and (not isinstance(result["level"], int) or isinstance(result["level"], bool) or not connection.execute("SELECT 1 FROM levels WHERE level = ?", (result["level"],)).fetchone()):
        raise ValueError("invalid level")
    if result["status"] == "insufficient_evidence" and result["level"] is not None:
        raise ValueError("insufficient evidence requires null level")
    refs = result["evidence_refs"]
    marks = ",".join("?" for _ in refs)
    if connection.execute("SELECT count(*) FROM evidence WHERE student_id = ? AND id IN (" + marks + ")", [student_id] + refs).fetchone()[0] != len(set(refs)):
        raise ValueError("invalid evidence refs")


def claim_next_job() -> Optional[dict]:
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT id FROM assessment_jobs WHERE status = 'queued' ORDER BY id LIMIT 1").fetchone()
        if not row:
            return None
        claimed = connection.execute("UPDATE assessment_jobs SET status = 'running', attempts = attempts + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'queued'", row)
        if not claimed.rowcount:
            return None
        connection.execute("INSERT INTO job_events (job_id, stage, detail) VALUES (?, ?, ?)", (row[0], "running", "claimed"))
    return get_job(row[0])


def fail_job(job_id: int, error: str) -> None:
    with connect() as connection:
        attempts = connection.execute("SELECT attempts FROM assessment_jobs WHERE id = ?", (job_id,)).fetchone()[0]
        status = "failed" if attempts >= 3 else "queued"  # initial attempt plus two retries
        connection.execute("UPDATE assessment_jobs SET status = ?, error = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, error, job_id))
        connection.execute("INSERT INTO job_events (job_id, stage, detail) VALUES (?, ?, ?)", (job_id, status, error))


def task_context(job_id: int) -> dict:
    job = get_job(job_id)
    if not job:
        raise ValueError("job does not exist")
    with connect() as connection:
        marks = ",".join("?" for _ in job["evidence_refs"])
        evidence = [dict(zip(("id", "evidence_type", "text", "filename", "media_type", "content"), row)) for row in connection.execute("SELECT id, evidence_type, text, filename, media_type, content FROM evidence WHERE id IN (" + marks + ")", job["evidence_refs"])]
    for item in evidence:
        if item["media_type"] in {"image/jpeg", "image/png"} and item["content"]:
            import base64
            item["image_data_url"] = "data:" + item["media_type"] + ";base64," + base64.b64encode(item["content"]).decode()
        item.pop("content", None)
    return {"job": job, "evidence": evidence, "rubric": current_rubric()}


def recover_running_jobs() -> int:
    with connect() as connection:
        rows = connection.execute("SELECT id FROM assessment_jobs WHERE status = 'running'").fetchall()
        for (job_id,) in rows:
            connection.execute("UPDATE assessment_jobs SET status = 'queued', error = 'worker restart recovery' WHERE id = ?", (job_id,))
            connection.execute("INSERT INTO job_events (job_id, stage, detail) VALUES (?, ?, ?)", (job_id, "queued", "worker restart recovery"))
    return len(rows)


def append_revision(result_id: int, result: dict) -> dict:
    with connect() as connection:
        row = connection.execute("SELECT job_id FROM assessment_results WHERE id = ?", (result_id,)).fetchone()
    if not row:
        raise ValueError("assessment result does not exist")
    return append_result(row[0], {key: value for key, value in result.items() if key not in {"id", "revision"}}, "manual_revision")


def record_event(job_id: int, stage: str, detail: str) -> None:
    with connect() as connection:
        connection.execute("INSERT INTO job_events (job_id, stage, detail) VALUES (?, ?, ?)", (job_id, stage, detail))
