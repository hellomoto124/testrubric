import sqlite3
import json
from contextlib import contextmanager
from pathlib import Path


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
            """
        )
        connection.executescript(
            "DELETE FROM levels; DELETE FROM skills; DELETE FROM competencies; DELETE FROM rubrics; DELETE FROM students; DELETE FROM classes; DELETE FROM schools;"
        )
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
