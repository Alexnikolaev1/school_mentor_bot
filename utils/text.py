"""Утилиты для работы с Telegram-сообщениями."""
import html
import logging
import re

from aiogram.types import Message

logger = logging.getLogger(__name__)

TELEGRAM_MAX_LENGTH = 4096


def escape_html(text: str) -> str:
    return html.escape(text)


async def send_long_message(
    message: Message,
    text: str,
    chunk_size: int = 4000,
    parse_mode: str = "HTML",
) -> None:
    """Разбивает длинные сообщения на части и отправляет."""
    if len(text) <= chunk_size:
        try:
            await message.answer(text, parse_mode=parse_mode)
        except Exception as e:
            logger.warning(f"HTML parse error, sending plain: {e}")
            await message.answer(_strip_html(text))
        return

    parts = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > chunk_size:
            parts.append(current)
            current = line
        else:
            current += ("\n" if current else "") + line
    if current:
        parts.append(current)

    for part in parts:
        try:
            await message.answer(part, parse_mode=parse_mode)
        except Exception:
            await message.answer(_strip_html(part))


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)
