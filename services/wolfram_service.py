"""
Сервис для работы с Wolfram Alpha API.
Short Answers API — быстрые числовые ответы.
Full Results API — пошаговые решения.
"""
import asyncio
import json
import logging
import urllib.parse
from typing import Optional, Tuple

import aiohttp

from config import WOLFRAM_APP_ID, WOLFRAM_SHORT_URL, WOLFRAM_FULL_URL
from utils.rate_limiter import wolfram_limiter
from utils.cache import get_cached, set_cached, make_key

logger = logging.getLogger(__name__)


async def wolfram_short_answer(query: str) -> Optional[str]:
    """
    Запрос к Short Answers API.
    Возвращает краткий ответ (число/выражение) или None.
    """
    cache_key = make_key(f"wolfram_short:{query}")
    cached = get_cached(cache_key)
    if cached:
        logger.debug("Wolfram short: из кэша")
        return cached

    await wolfram_limiter.acquire()

    params = {
        "i": query,
        "appid": WOLFRAM_APP_ID,
    }
    url = WOLFRAM_SHORT_URL + "?" + urllib.parse.urlencode(params)

    try:
        from services.http_client import get_session
        session = await get_session()
        async with session.get(url) as resp:
            if resp.status == 501:
                logger.debug(f"Wolfram short: нет ответа для '{query[:50]}'")
                return None
            if resp.status != 200:
                logger.warning(f"Wolfram short: status {resp.status}")
                return None
            text = await resp.text()
            text = text.strip()
            if text and "No short answer" not in text:
                set_cached(cache_key, text, ttl_days=30)
                return text
            return None

    except asyncio.TimeoutError:
        logger.warning("Wolfram short: таймаут")
        return None
    except aiohttp.ClientError as e:
        logger.error(f"Wolfram short: ошибка сети: {e}")
        return None


async def wolfram_step_by_step(query: str) -> Optional[str]:
    """
    Запрос к Full Results API для получения пошагового решения.
    Возвращает текст шагов или None.
    """
    cache_key = make_key(f"wolfram_steps:{query}")
    cached = get_cached(cache_key)
    if cached:
        logger.debug("Wolfram steps: из кэша")
        return cached

    await wolfram_limiter.acquire()

    params = {
        "input": query,
        "format": "plaintext",
        "output": "JSON",
        "appid": WOLFRAM_APP_ID,
        "podstate": "Step-by-step solution",
        "includepodid": "StepByStepSolution,Result,DecimalApproximation",
    }
    url = WOLFRAM_FULL_URL + "?" + urllib.parse.urlencode(params)

    try:
        from services.http_client import get_session
        session = await get_session()
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                logger.warning(f"Wolfram full: status {resp.status}")
                return None
            data = await resp.json(content_type=None)

    except asyncio.TimeoutError:
        logger.warning("Wolfram full: таймаут")
        return None
    except (aiohttp.ClientError, json.JSONDecodeError) as e:
        logger.error(f"Wolfram full: ошибка: {e}")
        return None

    # Парсим JSON-ответ Wolfram
    steps = _extract_steps_json(data)
    if steps:
        set_cached(cache_key, steps, ttl_days=30)
    return steps


def _extract_steps_json(data: dict) -> Optional[str]:
    """
    Извлекает шаги из JSON-ответа Wolfram Alpha Full Results API.
    """
    try:
        query_result = data.get("queryresult", {})
        if not query_result.get("success"):
            return None

        pods = query_result.get("pods", [])
        step_texts = []

        for pod in pods:
            pod_id = pod.get("id", "")
            title = pod.get("title", "")

            # Ищем поды со step-by-step решением
            if any(kw in pod_id.lower() or kw in title.lower()
                   for kw in ["step", "solution", "result", "decimal"]):
                subpods = pod.get("subpods", [])
                for sp in subpods:
                    pt = sp.get("plaintext", "").strip()
                    if pt:
                        step_texts.append(f"**{title}:**\n{pt}")

        return "\n\n".join(step_texts) if step_texts else None

    except (KeyError, TypeError) as e:
        logger.error(f"Wolfram: ошибка парсинга JSON: {e}")
        return None


async def solve_math_query(query: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Высокоуровневая функция: пытается получить ответ и шаги от Wolfram.
    Возвращает (short_answer, steps) — любое из них может быть None.
    """
    # Параллельно запрашиваем короткий ответ и шаги
    short_task = asyncio.create_task(wolfram_short_answer(query))
    steps_task = asyncio.create_task(wolfram_step_by_step(query))

    short = await short_task
    steps = await steps_task

    return short, steps


def is_math_subject(subject: str) -> bool:
    """Определяет, можно ли использовать Wolfram для данного предмета."""
    from config import WOLFRAM_SUBJECTS
    return subject.lower() in WOLFRAM_SUBJECTS


def is_math_task_type(task_type: str) -> bool:
    """Определяет, подходит ли тип задания для Wolfram."""
    return task_type.lower() in {"math", "algebra", "geometry", "physics", "chemistry", "informatics"}
