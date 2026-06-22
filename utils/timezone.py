"""Утилиты для работы с часовыми поясами."""
from datetime import datetime
from zoneinfo import ZoneInfo


def local_hour_minute(timezone: str) -> tuple[int, int]:
    """Возвращает (час, минута) в указанном часовом поясе."""
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")
    now = datetime.now(tz)
    return now.hour, now.minute


def is_study_time(study_time: str, timezone: str) -> bool:
    """
    Проверяет, совпадает ли текущее локальное время ученика с study_time (ЧЧ:ММ).
    Сравниваем только час — планировщик запускается раз в час.
    """
    try:
        hour, minute = map(int, study_time.split(":"))
    except (ValueError, AttributeError):
        hour, minute = 17, 0

    local_h, local_m = local_hour_minute(timezone)
    return local_h == hour
