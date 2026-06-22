"""
Модуль работы с базой данных SQLite.
Создаёт схему при первом запуске, выполняет миграции.
Синхронные функции — для внутреннего использования;
async-обёртки (a*) — для вызова из aiogram-хэндлеров.
"""
import asyncio
import sqlite3
import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Any, Callable, TypeVar

from config import DB_PATH

logger = logging.getLogger(__name__)

T = TypeVar("T")


def get_connection() -> sqlite3.Connection:
    """Возвращает соединение с БД с включёнными внешними ключами."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # лучше для конкурентного доступа
    return conn


def init_db() -> None:
    """Создаёт все таблицы если они ещё не существуют."""
    conn = get_connection()
    cursor = conn.cursor()

    # ─── Ученики ──────────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            user_id   INTEGER PRIMARY KEY,
            name      TEXT    NOT NULL DEFAULT '',
            grade     INTEGER NOT NULL DEFAULT 9,
            subjects  TEXT    NOT NULL DEFAULT '[]',
            level     TEXT    NOT NULL DEFAULT 'intermediate',
            timezone  TEXT    NOT NULL DEFAULT 'Europe/Moscow',
            study_time TEXT   NOT NULL DEFAULT '17:00',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ─── Родители ─────────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS parents (
            user_id INTEGER PRIMARY KEY,
            name    TEXT NOT NULL DEFAULT ''
        )
    """)

    # ─── Связь родитель–ученик ────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS parent_links (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id  INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            FOREIGN KEY(parent_id)  REFERENCES parents(user_id),
            FOREIGN KEY(student_id) REFERENCES students(user_id),
            UNIQUE(parent_id, student_id)
        )
    """)

    # ─── Лог домашних заданий ─────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS homework_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id  INTEGER  NOT NULL,
            subject     TEXT     NOT NULL,
            task_number TEXT     NOT NULL DEFAULT '1',
            correct     INTEGER  NOT NULL DEFAULT 0,
            max_score   INTEGER  NOT NULL DEFAULT 1,
            timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES students(user_id)
        )
    """)

    # ─── Результаты экзаменов ─────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exam_results (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            subject    TEXT    NOT NULL,
            exam_type  TEXT    NOT NULL,
            score      INTEGER NOT NULL DEFAULT 0,
            max_score  INTEGER NOT NULL DEFAULT 100,
            detailed   TEXT    NOT NULL DEFAULT '{}',
            timestamp  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES students(user_id)
        )
    """)

    # ─── Учебный план ────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS study_plan (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id    INTEGER NOT NULL,
            subject       TEXT    NOT NULL,
            topic         TEXT    NOT NULL,
            priority      INTEGER NOT NULL DEFAULT 1,
            completed     INTEGER NOT NULL DEFAULT 0,
            date_assigned TEXT    DEFAULT (DATE('now')),
            FOREIGN KEY(student_id) REFERENCES students(user_id)
        )
    """)

    # ─── Кэш диагностических тестов ──────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS diagnostic_cache (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            subject    TEXT NOT NULL,
            grade      INTEGER NOT NULL,
            questions  TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL
        )
    """)

    # ─── Общий кэш запросов ───────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            key        TEXT PRIMARY KEY,
            data       TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL
        )
    """)

    # ─── Коды приглашений ────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invite_codes (
            code       TEXT PRIMARY KEY,
            student_id INTEGER NOT NULL,
            used       INTEGER NOT NULL DEFAULT 0,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY(student_id) REFERENCES students(user_id)
        )
    """)

    # ─── Состояние диагностики (временное) ────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS diagnostic_sessions (
            user_id       INTEGER PRIMARY KEY,
            subject       TEXT    NOT NULL,
            questions     TEXT    NOT NULL,
            current_q     INTEGER NOT NULL DEFAULT 0,
            answers       TEXT    NOT NULL DEFAULT '[]',
            started_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ─── Состояние экзамена (временное) ───────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exam_sessions (
            user_id    INTEGER PRIMARY KEY,
            subject    TEXT    NOT NULL,
            exam_type  TEXT    NOT NULL,
            tasks      TEXT    NOT NULL,
            answers    TEXT    NOT NULL DEFAULT '[]',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ─── Контекст пользователя (TTS, напоминания) ─────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_context (
            user_id       INTEGER PRIMARY KEY,
            last_response TEXT,
            last_topic_id INTEGER,
            reminder_date TEXT,
            FOREIGN KEY(user_id) REFERENCES students(user_id)
        )
    """)

    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")


# ─── Async-обёртки ───────────────────────────────────────────────────────────

async def _run_sync(fn: Callable[..., T], *args, **kwargs) -> T:
    return await asyncio.to_thread(fn, *args, **kwargs)


async def aget_student(user_id: int) -> Optional[dict]:
    return await _run_sync(get_student, user_id)


async def aget_parent(user_id: int) -> Optional[dict]:
    return await _run_sync(get_parent, user_id)


async def aupsert_student(user_id: int, **kwargs) -> None:
    await _run_sync(upsert_student, user_id, **kwargs)


async def aupsert_parent(user_id: int, name: str) -> None:
    await _run_sync(upsert_parent, user_id, name)


# ─── Вспомогательные функции ─────────────────────────────────────────────────

def get_student(user_id: int) -> Optional[dict]:
    """Возвращает данные ученика или None если не зарегистрирован."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM students WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_student(user_id: int, **kwargs) -> None:
    """Создаёт или обновляет запись ученика."""
    conn = get_connection()
    existing = conn.execute("SELECT user_id FROM students WHERE user_id = ?", (user_id,)).fetchone()
    if existing:
        if kwargs:
            sets = ", ".join(f"{k} = ?" for k in kwargs)
            vals = list(kwargs.values()) + [user_id]
            conn.execute(f"UPDATE students SET {sets} WHERE user_id = ?", vals)
    else:
        conn.execute(
            "INSERT INTO students (user_id) VALUES (?)",
            (user_id,)
        )
        if kwargs:
            sets = ", ".join(f"{k} = ?" for k in kwargs)
            vals = list(kwargs.values()) + [user_id]
            conn.execute(f"UPDATE students SET {sets} WHERE user_id = ?", vals)
    conn.commit()
    conn.close()


def get_parent(user_id: int) -> Optional[dict]:
    """Возвращает данные родителя."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM parents WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_parent(user_id: int, name: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO parents (user_id, name) VALUES (?, ?)",
        (user_id, name)
    )
    conn.commit()
    conn.close()


def get_student_by_invite(code: str) -> Optional[int]:
    """Возвращает student_id для действующего кода приглашения."""
    conn = get_connection()
    row = conn.execute(
        "SELECT student_id FROM invite_codes WHERE code = ? AND used = 0 AND expires_at > CURRENT_TIMESTAMP",
        (code,)
    ).fetchone()
    conn.close()
    return row["student_id"] if row else None


def mark_invite_used(code: str) -> None:
    conn = get_connection()
    conn.execute("UPDATE invite_codes SET used = 1 WHERE code = ?", (code,))
    conn.commit()
    conn.close()


def link_parent_student(parent_id: int, student_id: int) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO parent_links (parent_id, student_id) VALUES (?, ?)",
        (parent_id, student_id)
    )
    conn.commit()
    conn.close()


def get_linked_students(parent_id: int) -> list:
    """Возвращает список учеников, привязанных к родителю."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT s.* FROM students s
        JOIN parent_links pl ON pl.student_id = s.user_id
        WHERE pl.parent_id = ?
    """, (parent_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def log_homework(student_id: int, subject: str, task_number: str, correct: bool, max_score: int = 1) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO homework_log (student_id, subject, task_number, correct, max_score) VALUES (?,?,?,?,?)",
        (student_id, subject, task_number, 1 if correct else 0, max_score)
    )
    conn.commit()
    conn.close()


def get_homework_stats(student_id: int, days: int = 7) -> list:
    """Статистика ДЗ за последние N дней, сгруппированная по предмету."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT subject,
               COUNT(*) as total,
               SUM(correct) as correct_count
        FROM homework_log
        WHERE student_id = ? AND timestamp >= DATETIME('now', ?)
        GROUP BY subject
    """, (student_id, f"-{days} days")).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_exam_result(student_id: int, subject: str, exam_type: str,
                     score: int, max_score: int, detailed: dict) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO exam_results (student_id, subject, exam_type, score, max_score, detailed) VALUES (?,?,?,?,?,?)",
        (student_id, subject, exam_type, score, max_score, json.dumps(detailed, ensure_ascii=False))
    )
    conn.commit()
    conn.close()


def get_exam_results(student_id: int, limit: int = 10) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM exam_results WHERE student_id = ? ORDER BY timestamp DESC LIMIT ?",
        (student_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_study_plan(student_id: int, plans: list[dict]) -> None:
    """Сохраняет учебный план (список тем)."""
    conn = get_connection()
    # Удаляем старые незавершённые задания по тем же предметам
    subjects = list({p["subject"] for p in plans})
    for s in subjects:
        conn.execute(
            "DELETE FROM study_plan WHERE student_id = ? AND subject = ? AND completed = 0",
            (student_id, s)
        )
    for p in plans:
        conn.execute(
            "INSERT INTO study_plan (student_id, subject, topic, priority) VALUES (?,?,?,?)",
            (student_id, p["subject"], p["topic"], p.get("priority", 1))
        )
    conn.commit()
    conn.close()


def get_study_plan(student_id: int) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM study_plan WHERE student_id = ? AND completed = 0 ORDER BY priority",
        (student_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def complete_study_topic(topic_id: int) -> None:
    conn = get_connection()
    conn.execute("UPDATE study_plan SET completed = 1 WHERE id = ?", (topic_id,))
    conn.commit()
    conn.close()


def get_next_study_topic(student_id: int) -> Optional[dict]:
    """Возвращает первую незавершённую тему учебного плана."""
    plan = get_study_plan(student_id)
    return plan[0] if plan else None


def create_invite_code(student_id: int, hours: int = 24) -> str:
    """Создаёт одноразовый код приглашения для родителя."""
    code = secrets.token_urlsafe(8).upper()
    expires_at = (datetime.utcnow() + timedelta(hours=hours)).isoformat()
    conn = get_connection()
    conn.execute(
        "INSERT INTO invite_codes (code, student_id, used, expires_at) VALUES (?,?,0,?)",
        (code, student_id, expires_at),
    )
    conn.commit()
    conn.close()
    return code


# ─── Контекст пользователя ───────────────────────────────────────────────────

def save_last_response(user_id: int, text: str, topic_id: int | None = None) -> None:
    conn = get_connection()
    conn.execute(
        """INSERT INTO user_context (user_id, last_response, last_topic_id)
           VALUES (?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
             last_response = excluded.last_response,
             last_topic_id = excluded.last_topic_id""",
        (user_id, text, topic_id),
    )
    conn.commit()
    conn.close()


def get_last_response(user_id: int) -> Optional[str]:
    conn = get_connection()
    row = conn.execute(
        "SELECT last_response FROM user_context WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return row["last_response"] if row and row["last_response"] else None


def get_active_topic_id(user_id: int) -> Optional[int]:
    conn = get_connection()
    row = conn.execute(
        "SELECT last_topic_id FROM user_context WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return row["last_topic_id"] if row and row["last_topic_id"] else None


def set_active_topic(user_id: int, topic_id: int) -> None:
    conn = get_connection()
    conn.execute(
        """INSERT INTO user_context (user_id, last_topic_id)
           VALUES (?, ?)
           ON CONFLICT(user_id) DO UPDATE SET last_topic_id = excluded.last_topic_id""",
        (user_id, topic_id),
    )
    conn.commit()
    conn.close()


def was_reminder_sent_today(user_id: int) -> bool:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn = get_connection()
    row = conn.execute(
        "SELECT reminder_date FROM user_context WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return bool(row and row["reminder_date"] == today)


def mark_reminder_sent(user_id: int) -> None:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn = get_connection()
    conn.execute(
        """INSERT INTO user_context (user_id, reminder_date)
           VALUES (?, ?)
           ON CONFLICT(user_id) DO UPDATE SET reminder_date = excluded.reminder_date""",
        (user_id, today),
    )
    conn.commit()
    conn.close()


def get_students_for_reminder() -> list[dict]:
    """Все зарегистрированные ученики с заполненным именем."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM students WHERE name != ''").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Сессии диагностики ───────────────────────────────────────────────────────

def save_diagnostic_session(user_id: int, subject: str, questions: list) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO diagnostic_sessions (user_id, subject, questions, current_q, answers) VALUES (?,?,?,0,'[]')",
        (user_id, subject, json.dumps(questions, ensure_ascii=False))
    )
    conn.commit()
    conn.close()


def get_diagnostic_session(user_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM diagnostic_sessions WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_diagnostic_session(user_id: int, current_q: int, answers: list) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE diagnostic_sessions SET current_q = ?, answers = ? WHERE user_id = ?",
        (current_q, json.dumps(answers, ensure_ascii=False), user_id)
    )
    conn.commit()
    conn.close()


def delete_diagnostic_session(user_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM diagnostic_sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# ─── Сессии экзамена ──────────────────────────────────────────────────────────

def save_exam_session(user_id: int, subject: str, exam_type: str, tasks: list) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO exam_sessions (user_id, subject, exam_type, tasks, answers) VALUES (?,?,?,?,'[]')",
        (user_id, subject, exam_type, json.dumps(tasks, ensure_ascii=False))
    )
    conn.commit()
    conn.close()


def get_exam_session(user_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM exam_sessions WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_exam_session(user_id: int, answers: list) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE exam_sessions SET answers = ? WHERE user_id = ?",
        (json.dumps(answers, ensure_ascii=False), user_id)
    )
    conn.commit()
    conn.close()


def delete_exam_session(user_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM exam_sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
