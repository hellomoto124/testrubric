from collections import Counter

from .database import DEMO_NOTICE, connect


def _median(values):
    values = sorted(value for value in values if value is not None)
    return values[(len(values) - 1) // 2] if values else None


def _scope(connection, scope, subject_id):
    if scope == "school":
        row = connection.execute(
            "SELECT id, name, is_simulated_test_data FROM schools WHERE id = ?",
            (subject_id,),
        ).fetchone()
        student_rows = connection.execute(
            """SELECT s.id FROM students s JOIN classes c ON c.id = s.class_id
            WHERE c.school_id = ? ORDER BY s.id""",
            (subject_id,),
        ).fetchall()
        subject = dict(zip(("id", "name", "is_simulated_test_data"), row)) if row else None
    elif scope == "class":
        row = connection.execute(
            "SELECT id, name, is_simulated_test_data FROM classes WHERE id = ?",
            (subject_id,),
        ).fetchone()
        student_rows = connection.execute(
            "SELECT id FROM students WHERE class_id = ? ORDER BY id", (subject_id,)
        ).fetchall()
        subject = dict(zip(("id", "name", "is_simulated_test_data"), row)) if row else None
    elif scope == "student":
        row = connection.execute(
            "SELECT id, anonymous_id, is_simulated_test_data FROM students WHERE id = ?",
            (subject_id,),
        ).fetchone()
        student_rows = [(subject_id,)] if row else []
        subject = dict(zip(("id", "anonymous_id", "is_simulated_test_data"), row)) if row else None
    else:
        return None, []
    if subject:
        subject["is_simulated_test_data"] = bool(subject["is_simulated_test_data"])
    return subject, [row[0] for row in student_rows]


def _latest_results(connection, student_ids):
    if not student_ids:
        return {}
    marks = ",".join("?" for _ in student_ids)
    rows = connection.execute(
        """SELECT j.student_id, j.skill_code, r.result, r.engine, j.id, r.revision
        FROM assessment_jobs_v2 j JOIN assessment_results_v2 r ON r.job_id = j.id
        WHERE j.student_id IN ("""
        + marks
        + """) AND j.status = 'succeeded'
        ORDER BY CASE WHEN r.engine = 'seed_demo_v2' THEN 0 ELSE 1 END,
        j.id, r.revision""",
        student_ids,
    ).fetchall()
    import json

    latest = {}
    for student_id, skill_code, payload, engine, job_id, revision in rows:
        latest[(student_id, skill_code)] = json.loads(payload) | {
            "engine": engine,
            "job_id": job_id,
            "revision": revision,
        }
    return latest


def _summarize(items, eligible_count):
    assessed = [
        item
        for item in items
        if item and item.get("score_state") in {"exact", "bounded"}
    ]
    exact_levels = [
        item.get("attained_level")
        for item in assessed
        if item.get("score_state") == "exact"
    ]
    statuses = Counter(
        item.get("target_status", "not_configured") for item in items if item
    )
    return {
        "median_level": _median(exact_levels),
        "assessed_count": len(assessed),
        "eligible_count": eligible_count,
        "coverage": len(assessed) / eligible_count if eligible_count else 0,
        "target_status_counts": dict(statuses),
        "score_points": [
            item["score_display"]
            for item in assessed
            if item.get("score_state") == "exact" and item.get("score_display") is not None
        ],
        "score_intervals": [
            {"lower": item["score_lower"], "upper": item["score_upper"]}
            for item in assessed
            if item.get("score_state") == "bounded"
            and item.get("score_lower") is not None
            and item.get("score_upper") is not None
        ],
    }


def dashboard(scope: str, subject_id: int):
    with connect() as connection:
        subject, student_ids = _scope(connection, scope, subject_id)
        if not subject:
            return None
        rubric = connection.execute(
            "SELECT id, code, scoring_version FROM rubric_versions_v2 WHERE code = 'kai_feng_yuyang_260910'"
        ).fetchone()
        results = _latest_results(connection, student_ids)
        goals = []
        for goal_id, goal_code, goal_name in connection.execute(
            "SELECT id, code, name FROM education_goals_v2 WHERE rubric_id = ? ORDER BY code",
            (rubric[0],),
        ):
            capabilities = []
            goal_items = []
            for capability_id, capability_code, capability_name, description in connection.execute(
                """SELECT id, code, name, description FROM capabilities_v2
                WHERE goal_id = ? ORDER BY code""",
                (goal_id,),
            ).fetchall():
                skills = []
                capability_items = []
                for skill_code, name_cn, name_en, subskill in connection.execute(
                    """SELECT code, name_cn, name_en, subskill FROM skills_v2
                    WHERE capability_id = ? ORDER BY code""",
                    (capability_id,),
                ):
                    skill_results = [results.get((student_id, skill_code)) for student_id in student_ids]
                    target = connection.execute(
                        """SELECT target_level, basic, mastery, excellent, target_version
                        FROM target_policies_v2 WHERE rubric_id = ? AND skill_code = ?
                        AND term = 'default' ORDER BY id DESC LIMIT 1""",
                        (rubric[0], skill_code),
                    ).fetchone()
                    summary = _summarize(skill_results, len(student_ids))
                    skill = {
                        "code": skill_code,
                        "name": name_cn,
                        "name_en": name_en,
                        "subskill": subskill,
                        "target_level": target[0],
                        "basic_level": target[1],
                        "mastery_level": target[2],
                        "excellent_level": target[3],
                        "target_version": target[4],
                        **summary,
                    }
                    if scope == "student":
                        skill["result"] = skill_results[0]
                    skills.append(skill)
                    capability_items.extend(item for item in skill_results if item)
                capability_summary = _summarize(
                    capability_items, len(student_ids) * len(skills)
                )
                capabilities.append(
                    {
                        "code": capability_code,
                        "name": capability_name,
                        "description": description,
                        "skills": skills,
                        **capability_summary,
                    }
                )
                goal_items.extend(capability_items)
            skill_count = sum(len(item["skills"]) for item in capabilities)
            goals.append(
                {
                    "code": goal_code,
                    "name": goal_name,
                    "capabilities": capabilities,
                    **_summarize(goal_items, len(student_ids) * skill_count),
                }
            )
    return {
        "data_notice": DEMO_NOTICE,
        "scope": {"type": scope, "id": subject_id},
        "subject": subject,
        "student_count": len(student_ids),
        "rubric_code": rubric[1],
        "scoring_version": rubric[2],
        "goals": goals,
    }
