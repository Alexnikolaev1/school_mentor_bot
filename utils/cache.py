"""
Кэширование запросов с TTL в SQLite.
Одинаковые запросы не дублируются к внешним API.
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Any

from config import DB_PATH, CACHE_TTL_DAYS, DIAGNOSTIC_CACHE_TTL_DAYS
import database as db

logger = logging.getLogger(__name__)


def make_key(text: str) -> str:
    """Создаёт SHA-256 хэш строки для использования как ключ кэша."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_cached(key: str) -> Optional[Any]:
    """
    Возвращает кэшированные данные по ключу или None если не найдено/просрочено.
    """
    import sqlite3
    conn = db.get_connection()
    row = conn.execute(
        "SELECT data FROM cache WHERE key = ? AND expires_at > CURRENT_TIMESTAMP",
        (key,)
    ).fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row["data"])
        except json.JSONDecodeError:
            return row["data"]
    return None


def set_cached(key: str, data: Any, ttl_days: int = CACHE_TTL_DAYS) -> None:
    """Сохраняет данные в кэш с указанным TTL в днях."""
    expires_at = (datetime.utcnow() + timedelta(days=ttl_days)).isoformat()
    data_str = json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else data
    conn = db.get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO cache (key, data, expires_at) VALUES (?,?,?)",
        (key, data_str, expires_at)
    )
    conn.commit()
    conn.close()
    logger.debug(f"Закэшировано: {key[:16]}... на {ttl_days} дней")


def cleanup_cache() -> None:
    """Удаляет просроченные записи кэша (вызывать при старте)."""
    conn = db.get_connection()
    deleted = conn.execute(
        "DELETE FROM cache WHERE expires_at <= CURRENT_TIMESTAMP"
    ).rowcount
    conn.commit()
    conn.close()
    if deleted:
        logger.info(f"Очистка кэша: удалено {deleted} просроченных записей")


# ─── Кэш диагностических тестов ──────────────────────────────────────────────

def get_diagnostic_cache(subject: str, grade: int) -> Optional[list]:
    """Возвращает кэшированные вопросы диагностики или None."""
    conn = db.get_connection()
    row = conn.execute(
        "SELECT questions FROM diagnostic_cache WHERE subject = ? AND grade = ? AND expires_at > CURRENT_TIMESTAMP ORDER BY id DESC LIMIT 1",
        (subject, grade)
    ).fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row["questions"])
        except Exception:
            return None
    return None


def set_diagnostic_cache(subject: str, grade: int, questions: list) -> None:
    """Кэширует вопросы диагностики на 7 дней."""
    expires_at = (datetime.utcnow() + timedelta(days=DIAGNOSTIC_CACHE_TTL_DAYS)).isoformat()
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO diagnostic_cache (subject, grade, questions, expires_at) VALUES (?,?,?,?)",
        (subject, grade, json.dumps(questions, ensure_ascii=False), expires_at)
    )
    conn.commit()
    conn.close()
