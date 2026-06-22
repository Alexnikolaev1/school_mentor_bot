"""
Конфигурация бота SCHOOL.AI
Все настройки берутся из переменных окружения
"""
import os
import tempfile
from pathlib import Path

# ─── Токены и ключи API ───────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
WOLFRAM_APP_ID = os.getenv("WOLFRAM_APP_ID", "")

# ─── Вебхук ───────────────────────────────────────────────────────────────────
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or os.getenv("RAILWAY_STATIC_URL", "")
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", 8000))

# ─── База данных ──────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "school.db")

# ─── Модели API ───────────────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-1.5-flash"
GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)
WOLFRAM_SHORT_URL = "https://api.wolframalpha.com/v1/result"
WOLFRAM_FULL_URL = "https://api.wolframalpha.com/v2/query"
GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_WHISPER_MODEL = "whisper-large-v3"

# ─── TTS ──────────────────────────────────────────────────────────────────────
TTS_VOICE = "ru-RU-SvetlanaNeural"
TTS_TMP_DIR = os.getenv("TTS_TMP_DIR", str(Path(tempfile.gettempdir()) / "school_bot_tts"))

# ─── Rate limiting ────────────────────────────────────────────────────────────
GEMINI_USER_RPM = 5
GEMINI_GLOBAL_RPM = 14
WOLFRAM_RPM = 5
GROQ_RPM = 10

# ─── TTL кэша ─────────────────────────────────────────────────────────────────
CACHE_TTL_DAYS = 30
DIAGNOSTIC_CACHE_TTL_DAYS = 7

# ─── Предметы ─────────────────────────────────────────────────────────────────
SUBJECTS = [
    "Математика",
    "Алгебра",
    "Геометрия",
    "Физика",
    "Химия",
    "Информатика",
    "Русский язык",
    "Литература",
    "История",
    "Обществознание",
    "Биология",
]

WOLFRAM_SUBJECTS = frozenset({
    "математика", "алгебра", "геометрия", "физика", "химия", "информатика",
})

# ─── Уровни обучения ──────────────────────────────────────────────────────────
LEVELS = {
    "beginner": "начальный",
    "intermediate": "средний",
    "advanced": "продвинутый",
}

# ─── Классы ───────────────────────────────────────────────────────────────────
GRADES = list(range(5, 12))

# ─── Часовые пояса ────────────────────────────────────────────────────────────
TIMEZONES = [
    "Europe/Moscow",
    "Europe/Kaliningrad",
    "Asia/Yekaterinburg",
    "Asia/Novosibirsk",
    "Asia/Krasnoyarsk",
    "Asia/Irkutsk",
    "Asia/Yakutsk",
    "Asia/Vladivostok",
]

# ─── Типы экзаменов ───────────────────────────────────────────────────────────
EXAM_TYPES = {"OGE": "ОГЭ (9 класс)", "EGE": "ЕГЭ (11 класс)"}

# ─── Планировщик ──────────────────────────────────────────────────────────────
SCHEDULER_INTERVAL_SEC = 1800  # проверка каждые 30 минут
