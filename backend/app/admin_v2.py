import json
import os
import time

from .database import connect


SETTINGS = {"academic_year", "term", "default_grade"}


def list_scoring_configs(skill_code: str):
    with connect() as connection:
        rubric_id = connection.execute(
            "SELECT id FROM rubric_versions_v2 WHERE code = 'kai_feng_yuyang_260910'"
        ).fetchone()[0]
        rows = connection.execute(
            """SELECT c.id, c.skill_code, c.version, c.status,
            c.calibration_status, c.is_simulated_test_data,
            count(g.id) AS group_count
            FROM scoring_configs_v2 c
            LEFT JOIN indicator_groups_v2 g ON g.config_id = c.id
            WHERE c.rubric_id = ? AND c.skill_code = ?
            GROUP BY c.id ORDER BY c.version DESC""",
            (rubric_id, skill_code),
        ).fetchall()
    return {
        "items": [
            dict(
                zip(
                    (
                        "id",
                        "skill_code",
                        "version",
                        "status",
                        "calibration_status",
                        "is_simulated_test_data",
                        "group_count",
                    ),
                    row,
                )
            )
            for row in rows
        ]
    }


def audit_report(limit: int):
    if type(limit) is not int or limit not in range(1, 101):
        raise ValueError("limit must be between 1 and 100")
    with connect() as connection:
        rows = connection.execute(
            """SELECT j.id, j.student_id, j.skill_code, j.status, j.rubric_code,
            j.config_snapshot, j.target_snapshot, j.attempts, j.created_at,
            (SELECT engine FROM assessment_results_v2 r
             WHERE r.job_id = j.id ORDER BY revision DESC LIMIT 1)
            FROM assessment_jobs_v2 j ORDER BY j.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    items = []
    for job_id, student_id, skill_code, status, rubric_code, config, target, attempts, created_at, engine in rows:
        config_snapshot = json.loads(config)
        target_snapshot = json.loads(target)
        items.append(
            {
                "job_id": job_id,
                "student_id": student_id,
                "skill_code": skill_code,
                "status": status,
                "rubric_code": rubric_code,
                "scoring_config_version": config_snapshot["version"],
                "target_version": target_snapshot["target_version"],
                "attempts": attempts,
                "engine": engine,
                "created_at": created_at,
            }
        )
    return {"items": items}


def record_worker_heartbeat():
    with connect() as connection:
        connection.execute(
            """INSERT INTO worker_runtime_v2 (id, heartbeat) VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET heartbeat = excluded.heartbeat""",
            (time.time(),),
        )


def system_status():
    with connect() as connection:
        settings = dict(connection.execute("SELECT key, value FROM system_settings_v2"))
        heartbeat = connection.execute(
            "SELECT heartbeat FROM worker_runtime_v2 WHERE id = 1"
        ).fetchone()
        counts = {
            "schools": connection.execute("SELECT count(*) FROM schools").fetchone()[0],
            "classes": connection.execute("SELECT count(*) FROM classes").fetchone()[0],
            "students": connection.execute("SELECT count(*) FROM students").fetchone()[0],
            "evidence": connection.execute("SELECT count(*) FROM evidence").fetchone()[0],
            "v2_results": connection.execute(
                "SELECT count(*) FROM assessment_results_v2"
            ).fetchone()[0],
        }
        jobs = {
            status: count
            for status, count in connection.execute(
                "SELECT status, count(*) FROM assessment_jobs_v2 GROUP BY status"
            )
        }
        failures = [
            {"job_id": job_id, "skill_code": skill_code, "error": error}
            for job_id, skill_code, error in connection.execute(
                """SELECT id, skill_code, error FROM assessment_jobs_v2
                WHERE status = 'failed' ORDER BY id DESC LIMIT 5"""
            )
        ]
        rubric = connection.execute(
            """SELECT r.code, r.scoring_version,
            (SELECT count(*) FROM skills_v2 s WHERE s.rubric_id = r.id)
            FROM rubric_versions_v2 r WHERE r.code = 'kai_feng_yuyang_260910'"""
        ).fetchone()
    online = bool(heartbeat and time.time() - heartbeat[0] < 12)
    return {
        "settings": settings,
        "model": {
            "name": os.getenv("OPENAI_COMPATIBLE_MODEL"),
            "base_url": os.getenv("OPENAI_COMPATIBLE_BASE_URL"),
            "api_key_configured": bool(os.getenv("OPENAI_COMPATIBLE_API_KEY")),
            "vision_enabled": os.getenv("VISION_ENABLED", "false").lower()
            in {"1", "true", "yes"},
            "demo_agent_mode": os.getenv("DEMO_AGENT_MODE", "true").lower()
            in {"1", "true", "yes"},
        },
        "worker": {
            "status": "online" if online else "offline",
            "last_heartbeat": heartbeat[0] if heartbeat else None,
            "jobs": jobs,
        },
        "database": {"status": "ok"},
        "data_counts": counts,
        "rubric": {
            "code": rubric[0],
            "scoring_version": rubric[1],
            "skills": rubric[2],
        },
        "recent_failures": failures,
    }


def update_settings(payload: dict):
    if (
        set(payload) != SETTINGS
        or any(not isinstance(value, str) or not value.strip() or len(value) > 60 for value in payload.values())
    ):
        raise ValueError("only academic_year, term and default_grade are allowed")
    with connect() as connection:
        connection.executemany(
            "UPDATE system_settings_v2 SET value = ? WHERE key = ?",
            [(payload[key].strip(), key) for key in SETTINGS],
        )
    return system_status()["settings"]
