import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DATABASE_PATH = Path(__file__).parent / "data" / "app.db"


def database_path() -> Path:
    return Path(os.getenv("FUTURE9_DATABASE_PATH", DEFAULT_DATABASE_PATH))


DATABASE_PATH = database_path()
DEMO_NOTICE = "模拟测试数据；AI自动评估；非正式。"


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
        connection.execute(
            "UPDATE schools SET name = ? WHERE is_simulated_test_data = 1 AND name = ?",
            ("凯风雨旸小学（模拟测试数据）", "模拟测试学校"),
        )
        if not connection.execute("SELECT count(*) FROM schools").fetchone()[0]:
            connection.execute(
                "INSERT INTO schools VALUES (1, ?, 1)",
                ("凯风雨旸小学（模拟测试数据）",),
            )
            connection.executemany(
                "INSERT INTO classes VALUES (?, 1, ?, 1)",
                [(number, f"模拟测试班级{number}") for number in range(1, 4)],
            )
            connection.executemany(
                "INSERT INTO students VALUES (?, ?, ?, 1)",
                [
                    (
                        number,
                        1 if number <= 7 else 2 if number <= 14 else 3,
                        f"模拟学生{number:02d}",
                    )
                    for number in range(1, 21)
                ],
            )
            rubric_id = connection.execute(
                "INSERT INTO rubrics (rubric_version, source_url, license_note, local_adaptation) VALUES (?, ?, ?, ?)",
                (
                    rubric["rubric_version"],
                    rubric["source_url"],
                    rubric["license_note"],
                    rubric["local_adaptation"],
                ),
            ).lastrowid
            for competency_position, competency in enumerate(rubric["competencies"]):
                competency_id = connection.execute(
                    "INSERT INTO competencies (rubric_id, position, name, description) VALUES (?, ?, ?, ?)",
                    (
                        rubric_id,
                        competency_position,
                        competency["name"],
                        competency["description"],
                    ),
                ).lastrowid
                for skill_position, skill in enumerate(competency["skills"]):
                    skill_id = connection.execute(
                        "INSERT INTO skills (competency_id, position, code, name) VALUES (?, ?, ?, ?)",
                        (competency_id, skill_position, skill["code"], skill["name"]),
                    ).lastrowid
                    connection.executemany(
                        "INSERT INTO levels (skill_id, level, descriptors) VALUES (?, ?, ?)",
                        [
                            (
                                skill_id,
                                level["level"],
                                json.dumps(level["descriptors"], ensure_ascii=False),
                            )
                            for level in skill["levels"]
                        ],
                    )
        _seed_demo_assessments(connection, rubric["rubric_version"])
        _initialize_v2(connection)


def _initialize_v2(connection):
    data = json.loads(
        (Path(__file__).parent / "data" / "kai_feng_yuyang_260910.json").read_text(
            encoding="utf-8"
        )
    )
    connection.executescript("""
    CREATE TABLE IF NOT EXISTS rubric_versions_v2 (id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, source TEXT NOT NULL, scoring_version TEXT NOT NULL DEFAULT 'anchor_interp_v1', is_simulated_test_data INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS education_goals_v2 (id INTEGER PRIMARY KEY, rubric_id INTEGER NOT NULL REFERENCES rubric_versions_v2(id), code TEXT UNIQUE NOT NULL, name TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS capabilities_v2 (id INTEGER PRIMARY KEY, rubric_id INTEGER NOT NULL REFERENCES rubric_versions_v2(id), goal_id INTEGER NOT NULL REFERENCES education_goals_v2(id), code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, description TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS skills_v2 (id INTEGER PRIMARY KEY, capability_id INTEGER NOT NULL REFERENCES capabilities_v2(id), code TEXT UNIQUE NOT NULL, subskill TEXT NOT NULL, name_cn TEXT NOT NULL, name_en TEXT NOT NULL, source TEXT NOT NULL, excel_row INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS levels_v2 (id INTEGER PRIMARY KEY, skill_id INTEGER NOT NULL REFERENCES skills_v2(id), level INTEGER NOT NULL, descriptors TEXT NOT NULL, UNIQUE(skill_id, level));
    CREATE TABLE IF NOT EXISTS scoring_configs_v2 (id INTEGER PRIMARY KEY, rubric_id INTEGER NOT NULL REFERENCES rubric_versions_v2(id), code TEXT UNIQUE NOT NULL, status TEXT NOT NULL, calibration_status TEXT NOT NULL, is_simulated_test_data INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS indicator_groups_v2 (id INTEGER PRIMARY KEY, config_id INTEGER NOT NULL REFERENCES scoring_configs_v2(id), skill_code TEXT NOT NULL, level INTEGER NOT NULL, code TEXT UNIQUE NOT NULL);
    CREATE TABLE IF NOT EXISTS indicators_v2 (id INTEGER PRIMARY KEY, group_id INTEGER NOT NULL REFERENCES indicator_groups_v2(id), code TEXT UNIQUE NOT NULL, source_text TEXT NOT NULL, weight REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS indicator_anchors_v2 (id INTEGER PRIMARY KEY, indicator_id INTEGER NOT NULL REFERENCES indicators_v2(id), score INTEGER NOT NULL, text TEXT NOT NULL, UNIQUE(indicator_id, score));
    CREATE TABLE IF NOT EXISTS target_policies_v2 (id INTEGER PRIMARY KEY, rubric_id INTEGER NOT NULL REFERENCES rubric_versions_v2(id), skill_code TEXT NOT NULL, grade TEXT NOT NULL, term TEXT NOT NULL, target_version TEXT NOT NULL DEFAULT 'v1', target_level INTEGER NOT NULL, basic INTEGER NOT NULL DEFAULT 2, mastery INTEGER NOT NULL DEFAULT 3, excellent INTEGER NOT NULL DEFAULT 4, UNIQUE(rubric_id, skill_code, grade, term, target_version));
    """)
    for table, column in (
        (
            "rubric_versions_v2",
            "scoring_version TEXT NOT NULL DEFAULT 'anchor_interp_v1'",
        ),
        ("skills_v2", "subskill TEXT NOT NULL DEFAULT ''"),
        ("target_policies_v2", "target_version TEXT NOT NULL DEFAULT 'v1'"),
        ("target_policies_v2", "basic INTEGER NOT NULL DEFAULT 2"),
        ("target_policies_v2", "mastery INTEGER NOT NULL DEFAULT 3"),
        ("target_policies_v2", "excellent INTEGER NOT NULL DEFAULT 4"),
    ):
        try:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column}")
        except sqlite3.OperationalError:
            pass
    connection.execute(
        "INSERT OR IGNORE INTO rubric_versions_v2 (code, source, is_simulated_test_data) VALUES (?, ?, 1)",
        (data["rubric_version"], "kai_feng_yuyang_260910.json"),
    )
    rubric_id = connection.execute(
        "SELECT id FROM rubric_versions_v2 WHERE code = ?", (data["rubric_version"],)
    ).fetchone()[0]
    goals = {}
    for goal in data["goals"]:
        connection.execute(
            "INSERT OR IGNORE INTO education_goals_v2 (rubric_id, code, name) VALUES (?, ?, ?)",
            (rubric_id, goal["code"], goal["name"]),
        )
        goals[goal["name"]] = connection.execute(
            "SELECT id FROM education_goals_v2 WHERE code = ?", (goal["code"],)
        ).fetchone()[0]
    for capability in data["capabilities"]:
        connection.execute(
            "INSERT OR IGNORE INTO capabilities_v2 (rubric_id, goal_id, code, name, description) VALUES (?, ?, ?, ?, ?)",
            (
                rubric_id,
                goals[capability["goal"]],
                capability["code"],
                capability["name"],
                capability["description"],
            ),
        )
        cap_id = connection.execute(
            "SELECT id FROM capabilities_v2 WHERE code = ?", (capability["code"],)
        ).fetchone()[0]
        for skill in capability["skills"]:
            connection.execute(
                "INSERT OR IGNORE INTO skills_v2 (capability_id, code, subskill, name_cn, name_en, source, excel_row) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    cap_id,
                    skill["code"],
                    skill["subskill"],
                    skill["name_cn"],
                    skill["name_en"],
                    skill["source"],
                    skill["excel_row"],
                ),
            )
            skill_id = connection.execute(
                "SELECT id FROM skills_v2 WHERE code = ?", (skill["code"],)
            ).fetchone()[0]
            connection.execute(
                "INSERT OR IGNORE INTO scoring_configs_v2 (rubric_id, code, status, calibration_status, is_simulated_test_data) VALUES (?, ?, 'published', 'uncalibrated', 1)",
                (rubric_id, skill["code"] + ".demo"),
            )
            config_id = connection.execute(
                "SELECT id FROM scoring_configs_v2 WHERE code = ?",
                (skill["code"] + ".demo",),
            ).fetchone()[0]
            for level in skill["levels"]:
                connection.execute(
                    "INSERT OR IGNORE INTO levels_v2 (skill_id, level, descriptors) VALUES (?, ?, ?)",
                    (
                        skill_id,
                        level["level"],
                        json.dumps(level["descriptors"], ensure_ascii=False),
                    ),
                )
                group_code = f"{skill['code']}.L{level['level']}"
                connection.execute(
                    "INSERT OR IGNORE INTO indicator_groups_v2 (config_id, skill_code, level, code) VALUES (?, ?, ?, ?)",
                    (config_id, skill["code"], level["level"], group_code),
                )
                group_id = connection.execute(
                    "SELECT id FROM indicator_groups_v2 WHERE code = ?", (group_code,)
                ).fetchone()[0]
                for index, descriptor in enumerate(level["descriptors"], 1):
                    code = f"{group_code}.I{index:02}"
                    connection.execute(
                        "INSERT OR IGNORE INTO indicators_v2 (group_id, code, source_text, weight) VALUES (?, ?, ?, ?)",
                        (group_id, code, descriptor, 1 / len(level["descriptors"])),
                    )
                    indicator_id = connection.execute(
                        "SELECT id FROM indicators_v2 WHERE code = ?", (code,)
                    ).fetchone()[0]
                    anchors = [
                        "有展示机会但未表现",
                        "大量支持下初步表现",
                        "支持下部分表现",
                        "按原描述大部分表现但有明确缺口",
                        "在原描述规定支持条件下完整表现",
                    ]
                    for score, text in enumerate(anchors):
                        connection.execute(
                            "INSERT OR IGNORE INTO indicator_anchors_v2 (indicator_id, score, text) VALUES (?, ?, ?)",
                            (indicator_id, score, f"{text}：{descriptor}"),
                        )
            connection.execute(
                "INSERT OR IGNORE INTO target_policies_v2 (rubric_id, skill_code, grade, term, target_level) VALUES (?, ?, '3-6', 'default', 3)",
                (rubric_id, skill["code"]),
            )


def v2_catalog():
    with connect() as connection:
        goals = []
        for goal_id, code, name in connection.execute(
            "SELECT id, code, name FROM education_goals_v2 ORDER BY code"
        ):
            capabilities = []
            for cap_id, cap_code, cap_name in connection.execute(
                "SELECT id, code, name FROM capabilities_v2 WHERE goal_id = ? ORDER BY code",
                (goal_id,),
            ):
                skills = [
                    dict(zip(("code", "name_cn"), row))
                    for row in connection.execute(
                        "SELECT code, name_cn FROM skills_v2 WHERE capability_id = ? ORDER BY code",
                        (cap_id,),
                    )
                ]
                capabilities.append(
                    {"code": cap_code, "name": cap_name, "skills": skills}
                )
            goals.append({"code": code, "name": name, "capabilities": capabilities})
        return {
            "goals": len(goals),
            "capabilities": sum(len(goal["capabilities"]) for goal in goals),
            "skills": sum(
                len(capability["skills"])
                for goal in goals
                for capability in goal["capabilities"]
            ),
            "levels": connection.execute("SELECT count(*) FROM levels_v2").fetchone()[
                0
            ],
            "indicators": connection.execute(
                "SELECT count(*) FROM indicators_v2"
            ).fetchone()[0],
            "hierarchy": goals,
            "legacy_mapping": {"status": "legacy_unscored"},
        }


def _seed_demo_assessments(connection, rubric_version: str) -> None:
    """Create the non-official demo baseline once; never replace later work."""
    students = connection.execute(
        "SELECT id FROM students WHERE is_simulated_test_data = 1 ORDER BY id"
    ).fetchall()
    competencies = connection.execute(
        "SELECT id, position FROM competencies ORDER BY position"
    ).fetchall()
    if len(students) != 20 or len(competencies) != 9:
        return
    for (student_id,) in students:
        refs = []
        for evidence_type in (
            "teacher_observation",
            "student_self_reflection",
            "student_work",
        ):
            row = connection.execute(
                "SELECT id FROM evidence WHERE student_id = ? AND evidence_type = ? AND text LIKE ? ORDER BY id LIMIT 1",
                (student_id, evidence_type, f"{DEMO_NOTICE}%"),
            ).fetchone()
            refs.append(
                row[0]
                if row
                else connection.execute(
                    "INSERT INTO evidence (student_id, evidence_type, text) VALUES (?, ?, ?)",
                    (student_id, evidence_type, f"{DEMO_NOTICE}{evidence_type}证据。"),
                ).lastrowid
            )
        for competency_id, _position in competencies:
            code = connection.execute(
                "SELECT code FROM skills WHERE competency_id = ? ORDER BY position LIMIT 1",
                (competency_id,),
            ).fetchone()[0]
            jobs = connection.execute(
                "SELECT id, status FROM assessment_jobs WHERE student_id = ? AND skill_code = ? AND engine = 'seed_demo' ORDER BY id",
                (student_id, code),
            ).fetchall()
            for duplicate_id, _status in jobs[1:]:
                connection.execute(
                    "DELETE FROM job_events WHERE job_id = ?", (duplicate_id,)
                )
                connection.execute(
                    "DELETE FROM assessment_results WHERE job_id = ?", (duplicate_id,)
                )
                connection.execute(
                    "DELETE FROM assessment_jobs WHERE id = ?", (duplicate_id,)
                )
            if jobs:
                job_id, status = jobs[0]
                if status != "succeeded":
                    connection.execute(
                        "UPDATE assessment_jobs SET status = 'succeeded', attempts = 1 WHERE id = ?",
                        (job_id,),
                    )
            else:
                job_id = connection.execute(
                    "INSERT INTO assessment_jobs (student_id, skill_code, evidence_refs, status, attempts, engine) VALUES (?, ?, ?, 'succeeded', 1, 'seed_demo')",
                    (student_id, code, json.dumps(refs)),
                ).lastrowid
            result = {
                "status": "assessed",
                "level": student_id % 6 + 1,
                "confidence": 0.6,
                "evidence_refs": refs,
                "rationale": DEMO_NOTICE,
                "next_step": "模拟测试数据：用于演示，不作正式结论。",
                "rubric_version": rubric_version,
                "model_run_id": f"seed-demo-{student_id}-{code}",
            }
            result_count = connection.execute(
                "SELECT count(*) FROM assessment_results WHERE job_id = ?", (job_id,)
            ).fetchone()[0]
            if result_count != 1:
                connection.execute(
                    "DELETE FROM assessment_results WHERE job_id = ?", (job_id,)
                )
                connection.execute(
                    "INSERT INTO assessment_results (job_id, revision, result) VALUES (?, 1, ?)",
                    (job_id, json.dumps(result, ensure_ascii=False)),
                )
            if not connection.execute(
                "SELECT 1 FROM job_events WHERE job_id = ? AND detail = 'seed_demo'",
                (job_id,),
            ).fetchone():
                connection.execute(
                    "INSERT INTO job_events (job_id, stage, detail) VALUES (?, 'succeeded', 'seed_demo')",
                    (job_id,),
                )


def current_rubric() -> dict:
    with connect() as connection:
        rubric = connection.execute(
            "SELECT rubric_version, source_url, license_note, local_adaptation FROM rubrics"
        ).fetchone()
        competencies = []
        for competency_id, name, description in connection.execute(
            "SELECT id, name, description FROM competencies ORDER BY position"
        ):
            skills = []
            for skill_id, code, skill_name in connection.execute(
                "SELECT id, code, name FROM skills WHERE competency_id = ? ORDER BY position",
                (competency_id,),
            ):
                levels = [
                    {"level": level, "descriptors": json.loads(descriptors)}
                    for level, descriptors in connection.execute(
                        "SELECT level, descriptors FROM levels WHERE skill_id = ? ORDER BY level",
                        (skill_id,),
                    )
                ]
                skills.append({"code": code, "name": skill_name, "levels": levels})
            competencies.append(
                {"name": name, "description": description, "skills": skills}
            )
    return dict(
        zip(
            ("rubric_version", "source_url", "license_note", "local_adaptation"), rubric
        )
    ) | {"competencies": competencies}


def _catalog(connection) -> list[dict]:
    competencies = []
    for competency_id, position, name, description in connection.execute(
        "SELECT id, position, name, description FROM competencies ORDER BY position"
    ):
        skills = [
            dict(zip(("id", "code", "name"), row))
            for row in connection.execute(
                "SELECT id, code, name FROM skills WHERE competency_id = ? ORDER BY position",
                (competency_id,),
            )
        ]
        competencies.append(
            {
                "id": competency_id,
                "position": position + 1,
                "name": name,
                "description": description,
                "skills": skills,
            }
        )
    return competencies


def _latest_results(connection) -> dict[tuple[int, str], dict]:
    rows = connection.execute(
        """
        SELECT j.id, j.student_id, j.skill_code, j.engine, r.id, r.revision, r.result, r.created_at
        FROM assessment_jobs j JOIN assessment_results r ON r.job_id = j.id
        WHERE r.revision = (SELECT MAX(revision) FROM assessment_results WHERE job_id = j.id)
        ORDER BY CASE WHEN j.engine = 'seed_demo' THEN 0 ELSE 1 END, j.id, r.revision
        """
    )
    latest = {}
    for (
        job_id,
        student_id,
        skill_code,
        engine,
        result_id,
        revision,
        result,
        created_at,
    ) in rows:
        latest[(student_id, skill_code)] = json.loads(result) | {
            "id": result_id,
            "job_id": job_id,
            "revision": revision,
            "engine": engine,
            "created_at": created_at,
        }
    return latest


def _summary(catalog: list[dict], results: dict, student_ids: list[int]) -> list[dict]:
    summaries = []
    for competency in catalog:
        assessed = []
        skill_count = len(student_ids) * len(competency["skills"])
        for student_id in student_ids:
            for skill in competency["skills"]:
                result = results.get((student_id, skill["code"]))
                if result and result["status"] == "assessed":
                    assessed.append(result["level"])
        summaries.append(
            {
                "position": competency["position"],
                "name": competency["name"],
                "description": competency["description"],
                "level": sorted(assessed)[(len(assessed) - 1) // 2]
                if assessed
                else None,
                "assessed_count": len(assessed),
                "skill_count": skill_count,
                "coverage": len(assessed) / skill_count if skill_count else 0,
            }
        )
    return summaries


def _coverage(catalog: list[dict], results: dict, student_ids: list[int]) -> dict:
    skill_count = len(student_ids) * sum(len(item["skills"]) for item in catalog)
    assessed_count = sum(
        result["status"] == "assessed"
        for (student_id, _), result in results.items()
        if student_id in student_ids
    )
    return {
        "assessed_count": assessed_count,
        "skill_count": skill_count,
        "coverage": assessed_count / skill_count if skill_count else 0,
    }


def school_dashboard() -> dict | None:
    with connect() as connection:
        school = connection.execute(
            "SELECT id, name, is_simulated_test_data FROM schools ORDER BY id LIMIT 1"
        ).fetchone()
        if not school:
            return None
        catalog, results = _catalog(connection), _latest_results(connection)
        classes = [
            dict(zip(("id", "name", "is_simulated_test_data"), row))
            for row in connection.execute(
                "SELECT id, name, is_simulated_test_data FROM classes WHERE school_id = ? ORDER BY id",
                (school[0],),
            )
        ]
        for classroom in classes:
            classroom["is_simulated_test_data"] = bool(
                classroom["is_simulated_test_data"]
            )
        students = [
            row[0] for row in connection.execute("SELECT id FROM students ORDER BY id")
        ]
        class_heatmap = []
        for classroom in classes:
            ids = [
                row[0]
                for row in connection.execute(
                    "SELECT id FROM students WHERE class_id = ? ORDER BY id",
                    (classroom["id"],),
                )
            ]
            class_heatmap.append(
                {"class": classroom, "competencies": _summary(catalog, results, ids)}
            )
        levels = [
            {
                "level": level,
                "count": sum(
                    result["level"] == level
                    for result in results.values()
                    if result["status"] == "assessed"
                ),
            }
            for level in range(1, 7)
        ]
        trend = []
        for date in sorted({result["created_at"][:10] for result in results.values()}):
            count = sum(
                result["status"] == "assessed" and result["created_at"].startswith(date)
                for result in results.values()
            )
            trend.append(
                {
                    "date": date,
                    "assessed_count": count,
                    "skill_count": len(students)
                    * sum(len(item["skills"]) for item in catalog),
                    "coverage": count
                    / (len(students) * sum(len(item["skills"]) for item in catalog)),
                }
            )
    return {
        "data_notice": DEMO_NOTICE,
        "school": {
            "id": school[0],
            "name": school[1],
            "is_simulated_test_data": bool(school[2]),
        },
        "competencies": _summary(catalog, results, students),
        "class_heatmap": class_heatmap,
        "level_distribution": levels,
        "coverage": _coverage(catalog, results, students),
        "trend": trend,
    }


def class_dashboard(class_id: int) -> dict | None:
    with connect() as connection:
        classroom = connection.execute(
            "SELECT id, school_id, name, is_simulated_test_data FROM classes WHERE id = ?",
            (class_id,),
        ).fetchone()
        if not classroom:
            return None
        catalog, results = _catalog(connection), _latest_results(connection)
        students = [
            dict(zip(("id", "anonymous_id", "is_simulated_test_data"), row))
            for row in connection.execute(
                "SELECT id, anonymous_id, is_simulated_test_data FROM students WHERE class_id = ? ORDER BY id",
                (class_id,),
            )
        ]
        for student in students:
            student["is_simulated_test_data"] = bool(student["is_simulated_test_data"])
        matrix = [
            student | {"competencies": _summary(catalog, results, [student["id"]])}
            for student in students
        ]
    return {
        "data_notice": DEMO_NOTICE,
        "class": {
            "id": classroom[0],
            "school_id": classroom[1],
            "name": classroom[2],
            "is_simulated_test_data": bool(classroom[3]),
        },
        "students": matrix,
        "competencies": _summary(
            catalog, results, [student["id"] for student in students]
        ),
        "coverage": _coverage(
            catalog, results, [student["id"] for student in students]
        ),
    }


def student_profile(student_id: int) -> dict | None:
    with connect() as connection:
        student = connection.execute(
            "SELECT id, class_id, anonymous_id, is_simulated_test_data FROM students WHERE id = ?",
            (student_id,),
        ).fetchone()
        if not student:
            return None
        catalog, results = _catalog(connection), _latest_results(connection)
        skills = [
            {
                "competency": competency["name"],
                "code": skill["code"],
                "name": skill["name"],
                "result": results.get((student_id, skill["code"])),
            }
            for competency in catalog
            for skill in competency["skills"]
        ]
        evidence = [
            dict(
                zip(
                    (
                        "id",
                        "evidence_type",
                        "text",
                        "filename",
                        "media_type",
                        "created_at",
                    ),
                    row,
                )
            )
            for row in connection.execute(
                "SELECT id, evidence_type, text, filename, media_type, created_at FROM evidence WHERE student_id = ? ORDER BY created_at, id",
                (student_id,),
            )
        ]
    return {
        "data_notice": DEMO_NOTICE,
        "student": {
            "id": student[0],
            "class_id": student[1],
            "anonymous_id": student[2],
            "is_simulated_test_data": bool(student[3]),
        },
        "competencies": _summary(catalog, results, [student_id]),
        "skills": skills,
        "evidence_timeline": evidence,
    }


def demo_context() -> dict:
    with connect() as connection:
        school = connection.execute(
            "SELECT id, name, is_simulated_test_data FROM schools ORDER BY id LIMIT 1"
        ).fetchone()
        classes = [
            dict(zip(("id", "school_id", "name", "is_simulated_test_data"), row))
            for row in connection.execute(
                "SELECT id, school_id, name, is_simulated_test_data FROM classes ORDER BY id"
            )
        ]
        students = [
            dict(zip(("id", "class_id", "anonymous_id", "is_simulated_test_data"), row))
            for row in connection.execute(
                "SELECT id, class_id, anonymous_id, is_simulated_test_data FROM students ORDER BY id"
            )
        ]
        for item in classes + students:
            item["is_simulated_test_data"] = bool(item["is_simulated_test_data"])
    return {
        "data_notice": DEMO_NOTICE,
        "school": {
            "id": school[0],
            "name": school[1],
            "is_simulated_test_data": bool(school[2]),
        },
        "classes": classes,
        "students": students,
    }


def create_evidence(
    student_id: int,
    evidence_type: str,
    text: str,
    filename: str | None = None,
    media_type: str | None = None,
    content: bytes | None = None,
) -> dict:
    with connect() as connection:
        if not connection.execute(
            "SELECT 1 FROM students WHERE id = ?", (student_id,)
        ).fetchone():
            raise ValueError("student does not exist")
        evidence_id = connection.execute(
            "INSERT INTO evidence (student_id, evidence_type, text, filename, media_type, content) VALUES (?, ?, ?, ?, ?, ?)",
            (student_id, evidence_type, text, filename, media_type, content),
        ).lastrowid
        row = connection.execute(
            "SELECT id, student_id, evidence_type, text, filename, media_type FROM evidence WHERE id = ?",
            (evidence_id,),
        ).fetchone()
    return dict(
        zip(
            ("id", "student_id", "evidence_type", "text", "filename", "media_type"), row
        )
    )


def create_job(student_id: int, skill_code: str, evidence_refs: list) -> dict:
    with connect() as connection:
        if (
            not connection.execute(
                "SELECT 1 FROM students WHERE id = ?", (student_id,)
            ).fetchone()
            or not connection.execute(
                "SELECT 1 FROM skills WHERE code = ?", (skill_code,)
            ).fetchone()
        ):
            raise ValueError("student or skill does not exist")
        marks = ",".join("?" for _ in evidence_refs)
        if not evidence_refs or connection.execute(
            "SELECT count(*) FROM evidence WHERE student_id = ? AND id IN ("
            + marks
            + ")",
            [student_id] + evidence_refs,
        ).fetchone()[0] != len(set(evidence_refs)):
            raise ValueError("evidence refs do not exist for student")
        job_id = connection.execute(
            "INSERT INTO assessment_jobs (student_id, skill_code, evidence_refs) VALUES (?, ?, ?)",
            (student_id, skill_code, json.dumps(evidence_refs)),
        ).lastrowid
    return get_job(job_id)


def get_job(job_id: int) -> dict | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT id, student_id, skill_code, evidence_refs, status, attempts, engine, error FROM assessment_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if not row:
            return None
        results = [
            dict(json.loads(result), id=result_id, revision=revision)
            for result_id, revision, result in connection.execute(
                "SELECT id, revision, result FROM assessment_results WHERE job_id = ? ORDER BY revision",
                (job_id,),
            )
        ]
        events = [
            dict(zip(("id", "stage", "detail"), event))
            for event in connection.execute(
                "SELECT id, stage, detail FROM job_events WHERE job_id = ? ORDER BY id",
                (job_id,),
            )
        ]
    job = dict(
        zip(
            (
                "id",
                "student_id",
                "skill_code",
                "evidence_refs",
                "status",
                "attempts",
                "engine",
                "error",
            ),
            row,
        )
    )
    job["evidence_refs"] = json.loads(job["evidence_refs"])
    job["results"] = results
    job["events"] = events
    return job


def append_result(job_id: int, result: dict, engine: str) -> dict:
    with connect() as connection:
        row = connection.execute(
            "SELECT student_id FROM assessment_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if not row:
            raise ValueError("job does not exist")
        _validate_result(connection, row[0], result)
        revision = (
            connection.execute(
                "SELECT count(*) FROM assessment_results WHERE job_id = ?", (job_id,)
            ).fetchone()[0]
            + 1
        )
        connection.execute(
            "INSERT INTO assessment_results (job_id, revision, result) VALUES (?, ?, ?)",
            (job_id, revision, json.dumps(result, ensure_ascii=False)),
        )
        connection.execute(
            "UPDATE assessment_jobs SET status = 'succeeded', engine = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (engine, job_id),
        )
        connection.execute(
            "INSERT INTO job_events (job_id, stage, detail) VALUES (?, ?, ?)",
            (job_id, "succeeded", engine),
        )
    return get_job(job_id)


def _validate_result(connection, student_id: int, result: dict) -> None:
    required = {
        "status",
        "level",
        "confidence",
        "evidence_refs",
        "rationale",
        "next_step",
        "rubric_version",
        "model_run_id",
    }
    text_fields = ("rationale", "next_step", "model_run_id")
    if (
        not required.issubset(result)
        or result["status"] not in {"assessed", "insufficient_evidence"}
        or not isinstance(result["confidence"], (int, float))
        or isinstance(result["confidence"], bool)
        or not 0 <= result["confidence"] <= 1
        or not isinstance(result["evidence_refs"], list)
        or not result["evidence_refs"]
        or any(type(ref) is not int for ref in result["evidence_refs"])
        or len(set(result["evidence_refs"])) != len(result["evidence_refs"])
        or any(
            not isinstance(result[field], str) or not result[field].strip()
            for field in text_fields
        )
    ):
        raise ValueError("invalid assessment result")
    version = connection.execute("SELECT rubric_version FROM rubrics").fetchone()[0]
    if result["rubric_version"] != version:
        raise ValueError("invalid rubric version")
    if result["status"] == "assessed" and (
        not isinstance(result["level"], int)
        or isinstance(result["level"], bool)
        or not connection.execute(
            "SELECT 1 FROM levels WHERE level = ?", (result["level"],)
        ).fetchone()
    ):
        raise ValueError("invalid level")
    if result["status"] == "insufficient_evidence" and result["level"] is not None:
        raise ValueError("insufficient evidence requires null level")
    refs = result["evidence_refs"]
    marks = ",".join("?" for _ in refs)
    if connection.execute(
        "SELECT count(*) FROM evidence WHERE student_id = ? AND id IN (" + marks + ")",
        [student_id] + refs,
    ).fetchone()[0] != len(set(refs)):
        raise ValueError("invalid evidence refs")


def claim_next_job() -> dict | None:
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id FROM assessment_jobs WHERE status = 'queued' ORDER BY id LIMIT 1"
        ).fetchone()
        if not row:
            return None
        claimed = connection.execute(
            "UPDATE assessment_jobs SET status = 'running', attempts = attempts + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'queued'",
            row,
        )
        if not claimed.rowcount:
            return None
        connection.execute(
            "INSERT INTO job_events (job_id, stage, detail) VALUES (?, ?, ?)",
            (row[0], "running", "claimed"),
        )
    return get_job(row[0])


def fail_job(job_id: int, error: str) -> None:
    with connect() as connection:
        attempts = connection.execute(
            "SELECT attempts FROM assessment_jobs WHERE id = ?", (job_id,)
        ).fetchone()[0]
        status = (
            "failed" if attempts >= 3 else "queued"
        )  # initial attempt plus two retries
        connection.execute(
            "UPDATE assessment_jobs SET status = ?, error = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, error, job_id),
        )
        connection.execute(
            "INSERT INTO job_events (job_id, stage, detail) VALUES (?, ?, ?)",
            (job_id, status, error),
        )


def task_context(job_id: int) -> dict:
    job = get_job(job_id)
    if not job:
        raise ValueError("job does not exist")
    with connect() as connection:
        marks = ",".join("?" for _ in job["evidence_refs"])
        evidence = [
            dict(
                zip(
                    (
                        "id",
                        "evidence_type",
                        "text",
                        "filename",
                        "media_type",
                        "content",
                    ),
                    row,
                )
            )
            for row in connection.execute(
                "SELECT id, evidence_type, text, filename, media_type, content FROM evidence WHERE id IN ("
                + marks
                + ")",
                job["evidence_refs"],
            )
        ]
    for item in evidence:
        if item["media_type"] in {"image/jpeg", "image/png"} and item["content"]:
            import base64

            item["image_data_url"] = (
                "data:"
                + item["media_type"]
                + ";base64,"
                + base64.b64encode(item["content"]).decode()
            )
        item.pop("content", None)
    return {"job": job, "evidence": evidence, "rubric": current_rubric()}


def recover_running_jobs() -> int:
    with connect() as connection:
        rows = connection.execute(
            "SELECT id FROM assessment_jobs WHERE status = 'running'"
        ).fetchall()
        for (job_id,) in rows:
            connection.execute(
                "UPDATE assessment_jobs SET status = 'queued', error = 'worker restart recovery' WHERE id = ?",
                (job_id,),
            )
            connection.execute(
                "INSERT INTO job_events (job_id, stage, detail) VALUES (?, ?, ?)",
                (job_id, "queued", "worker restart recovery"),
            )
    return len(rows)


def append_revision(result_id: int, result: dict) -> dict:
    with connect() as connection:
        row = connection.execute(
            "SELECT job_id FROM assessment_results WHERE id = ?", (result_id,)
        ).fetchone()
    if not row:
        raise ValueError("assessment result does not exist")
    return append_result(
        row[0],
        {key: value for key, value in result.items() if key not in {"id", "revision"}},
        "manual_revision",
    )


def record_event(job_id: int, stage: str, detail: str) -> None:
    with connect() as connection:
        connection.execute(
            "INSERT INTO job_events (job_id, stage, detail) VALUES (?, ?, ?)",
            (job_id, stage, detail),
        )
