import sqlite3
from pathlib import Path


DATABASE_PATH = Path(__file__).parent / "data" / "app.db"


def connect() -> sqlite3.Connection:
    return sqlite3.connect(DATABASE_PATH)


def initialize() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schools (id INTEGER PRIMARY KEY, name TEXT NOT NULL, is_simulated_test_data INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS classes (id INTEGER PRIMARY KEY, school_id INTEGER NOT NULL, name TEXT NOT NULL, is_simulated_test_data INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL, anonymous_id TEXT NOT NULL, is_simulated_test_data INTEGER NOT NULL);
            """
        )
        if connection.execute("SELECT count(*) FROM schools").fetchone()[0]:
            return
        connection.execute("INSERT INTO schools VALUES (1, ?, 1)", ("模拟测试学校",))
        connection.executemany(
            "INSERT INTO classes VALUES (?, 1, ?, 1)",
            [(number, f"模拟测试班级{number}") for number in range(1, 4)],
        )
        connection.executemany(
            "INSERT INTO students VALUES (?, ?, ?, 1)",
            [(number, (number - 1) // 10 + 1, f"模拟学生{number:02d}") for number in range(1, 31)],
        )
