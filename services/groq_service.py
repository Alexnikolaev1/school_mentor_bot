"""
Сервис транскрибации голосовых сообщений через Groq Whisper Large v3.
"""
import logging
from typing import Optional

from config import GROQ_API_KEY, GROQ_TRANSCRIPTION_URL, GROQ_WHISPER_MODEL, GROQ_RPM
from utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

groq_limiter = RateLimiter(max_calls=GROQ_RPM, window_seconds=60.0)


async def transcribe_audio(audio_data: bytes, filename: str = "voice.ogg") -> Optional[str]:
    """
    Преобразует аудиофайл в текст через Groq Whisper.
    
    Args:
        audio_data: байты аудиофайла (OGG/MP3/WAV)
        filename: имя файла (влияет на определение формата)
    Returns:
        Транскрипция или None при ошибке
    """
    if not GROQ_API_KEY:
        logger.warning("Groq API key не задан")
        return None

    await groq_limiter.acquire()

    try:
        import aiohttp
        from services.http_client import get_session

        form = aiohttp.FormData()
        form.add_field(
            "file",
            audio_data,
            filename=filename,
            content_type="audio/ogg"
        )
        form.add_field("model", GROQ_WHISPER_MODEL)
        form.add_field("language", "ru")
        form.add_field("response_format", "json")

        headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}

        session = await get_session()
        async with session.post(
            GROQ_TRANSCRIPTION_URL,
            data=form,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"Groq Whisper: status {resp.status}, {text[:200]}")
                return None

            data = await resp.json()
            transcript = data.get("text", "").strip()
            if not transcript:
                logger.warning("Groq Whisper: пустая транскрипция")
                return None

            logger.info(f"Groq: транскрибировано {len(transcript)} символов")
            return transcript

    except aiohttp.ClientError as e:
        logger.error(f"Groq Whisper: ошибка сети: {e}")
        return None
    except Exception as e:
        logger.error(f"Groq Whisper: неизвестная ошибка: {e}")
        return None
