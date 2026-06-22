"""Глобальная обработка ошибок в хэндлерах."""
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
            logger.exception(f"Ошибка в хэндлере: {e}")
            if isinstance(event, Message):
                await event.answer(
                    "⚠️ Произошла ошибка. Попробуй ещё раз или напиши /help."
                )
            return None
