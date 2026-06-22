"""
Асинхронный rate limiter на основе токен-баклета.
Защищает от превышения квот API.
"""
import asyncio
import time
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter.
    max_calls — максимум запросов в window_seconds секунд.
    """

    def __init__(self, max_calls: int, window_seconds: float = 60.0):
        self.max_calls = max_calls
        self.window = window_seconds
        self._calls: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """
        Ждёт, пока не освободится слот.
        Возвращает время ожидания в секундах (0 если не ждали).
        """
        async with self._lock:
            now = time.monotonic()
            # Удаляем старые вызовы за пределами окна
            self._calls = [t for t in self._calls if now - t < self.window]

            if len(self._calls) >= self.max_calls:
                # Нужно подождать до освобождения самого старого слота
                oldest = self._calls[0]
                wait = self.window - (now - oldest) + 0.05
                logger.debug(f"Rate limit: ждём {wait:.1f}с")
                await asyncio.sleep(wait)
                self._calls = [t for t in self._calls if time.monotonic() - t < self.window]

            self._calls.append(time.monotonic())
            return 0.0


class PerUserRateLimiter:
    """
    Rate limiter, отдельный для каждого пользователя + глобальный.
    """

    def __init__(self, user_max: int, global_max: int, window: float = 60.0):
        self._user_limiters: dict[int, RateLimiter] = defaultdict(
            lambda: RateLimiter(user_max, window)
        )
        self._global = RateLimiter(global_max, window)

    async def acquire(self, user_id: int) -> None:
        """Ждёт разрешения для данного user_id."""
        # Сначала глобальный, потом пользовательский
        await self._global.acquire()
        await self._user_limiters[user_id].acquire()


# ─── Глобальные экземпляры ────────────────────────────────────────────────────
from config import GEMINI_USER_RPM, GEMINI_GLOBAL_RPM, WOLFRAM_RPM

gemini_limiter = PerUserRateLimiter(
    user_max=GEMINI_USER_RPM,
    global_max=GEMINI_GLOBAL_RPM,
    window=60.0
)

wolfram_limiter = RateLimiter(max_calls=WOLFRAM_RPM, window_seconds=60.0)
