"""
Озвучка ответов через Microsoft Edge TTS.
Голос: ru-RU-SvetlanaNeural (женский, спокойный).
Временные файлы сохраняются в /tmp, удаляются после отправки.
"""
import asyncio
import logging
import os
import tempfile
import uuid
from typing import Optional

from config import TTS_VOICE, TTS_TMP_DIR

logger = logging.getLogger(__name__)

# Создаём директорию для TTS если нет
os.makedirs(TTS_TMP_DIR, exist_ok=True)


async def text_to_speech(text: str) -> Optional[str]:
    """
    Синтезирует речь из текста.
    
    Returns:
        Путь к OGG файлу или None при ошибке
    """
    try:
        import edge_tts
    except ImportError:
        logger.error("edge-tts не установлен")
        return None

    # Ограничиваем длину текста (edge-tts имеет лимиты)
    if len(text) > 3000:
        text = text[:3000] + "... [текст сокращён]"

    # Очищаем от markdown-символов для лучшего произношения
    clean_text = _clean_for_tts(text)

    # Генерируем уникальное имя файла
    filename = os.path.join(TTS_TMP_DIR, f"tts_{uuid.uuid4().hex}.mp3")

    try:
        communicate = edge_tts.Communicate(clean_text, TTS_VOICE)
        await communicate.save(filename)
        logger.debug(f"TTS: сохранён {filename}")
        return filename

    except Exception as e:
        logger.error(f"TTS: ошибка генерации: {e}")
        if os.path.exists(filename):
            os.remove(filename)
        return None


def delete_tts_file(filepath: str) -> None:
    """Удаляет временный TTS файл."""
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
            logger.debug(f"TTS: удалён {filepath}")
    except OSError as e:
        logger.warning(f"TTS: не удалось удалить {filepath}: {e}")


def _clean_for_tts(text: str) -> str:
    """Очищает текст от markdown для TTS."""
    import re
    # Убираем markdown-символы
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # **bold**
    text = re.sub(r'\*(.+?)\*', r'\1', text)         # *italic*
    text = re.sub(r'`(.+?)`', r'\1', text)           # `code`
    text = re.sub(r'#{1,6}\s*', '', text)             # ### заголовки
    text = re.sub(r'\n{3,}', '\n\n', text)           # много пустых строк
    text = re.sub(r'📌|✅|❌|💡|📝|🎓|📚|📊|⚙️|📈', '', text)  # эмодзи
    return text.strip()
