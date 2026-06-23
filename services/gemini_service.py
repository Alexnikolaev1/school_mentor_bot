"""
Сервис для работы с Google Gemini API.
Поддерживает текстовые запросы и мультимодальный (vision) режим.
"""
import asyncio
import base64
import json
import logging
from typing import Optional

import aiohttp

from config import GEMINI_API_KEY, GEMINI_API_URL, GEMINI_MODEL
from utils.rate_limiter import gemini_limiter
from utils.cache import get_cached, set_cached, make_key

logger = logging.getLogger(__name__)


async def call_gemini(
    prompt: str,
    user_id: int = 0,
    image_data: bytes = None,
    image_mime: str = "image/jpeg",
    use_cache: bool = True,
    cache_ttl: int = 30,
) -> Optional[str]:
    """
    Отправляет запрос в Gemini API.
    
    Args:
        prompt: текстовый промт
        user_id: для rate limiting
        image_data: байты изображения (для vision)
        image_mime: MIME-тип изображения
        use_cache: кэшировать ли результат
        cache_ttl: TTL кэша в днях
    Returns:
        Текст ответа или None при ошибке
    """
    # Проверка кэша для текстовых запросов
    if use_cache and not image_data:
        cache_key = make_key(f"gemini:{prompt}")
        cached = get_cached(cache_key)
        if cached:
            logger.debug("Gemini: ответ из кэша")
            return cached

    # Применяем rate limiting
    await gemini_limiter.acquire(user_id)

    # Формируем тело запроса
    parts: list[dict] = []

    if image_data:
        parts.append({
            "inline_data": {
                "mime_type": image_mime,
                "data": base64.b64encode(image_data).decode("utf-8")
            }
        })

    parts.append({"text": prompt})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 2048,
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
    }

    url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"

    try:
        from services.http_client import get_session
        session = await get_session()
        async with session.post(url, json=payload) as resp:
            if resp.status == 429:
                logger.warning("Gemini: превышен rate limit (429)")
                await asyncio.sleep(10)
                return None

            if resp.status != 200:
                text = await resp.text()
                logger.error(
                    f"Gemini API error {resp.status} (model={GEMINI_MODEL}): {text[:400]}"
                )
                if resp.status == 404:
                    logger.error(
                        "Модель не найдена. Задай GEMINI_MODEL=gemini-2.5-flash "
                        "или gemini-3.5-flash в переменных окружения."
                    )
                return None

            data = await resp.json()

    except asyncio.TimeoutError:
        logger.error("Gemini: таймаут запроса")
        return None
    except aiohttp.ClientError as e:
        logger.error(f"Gemini: ошибка сети: {e}")
        return None

    # Извлекаем текст из ответа
    try:
        candidates = data.get("candidates", [])
        if not candidates:
            logger.warning(f"Gemini: нет кандидатов. ответ: {data}")
            return None

        content = candidates[0].get("content", {})
        parts_out = content.get("parts", [])
        result = "".join(p.get("text", "") for p in parts_out).strip()

        if not result:
            logger.warning("Gemini: пустой ответ")
            return None

        # Кэшируем
        if use_cache and not image_data:
            set_cached(cache_key, result, ttl_days=cache_ttl)

        return result

    except (KeyError, IndexError, TypeError) as e:
        logger.error(f"Gemini: ошибка парсинга ответа: {e}, data: {str(data)[:300]}")
        return None


async def call_gemini_json(
    prompt: str,
    user_id: int = 0,
    image_data: bytes = None,
    image_mime: str = "image/jpeg",
    use_cache: bool = True,
) -> Optional[dict]:
    """
    Запрос к Gemini с ожиданием JSON-ответа.
    Автоматически парсит и очищает JSON из ответа.
    """
    result = await call_gemini(
        prompt=prompt,
        user_id=user_id,
        image_data=image_data,
        image_mime=image_mime,
        use_cache=use_cache,
    )
    if not result:
        return None

    # Пробуем извлечь JSON из ответа
    # Gemini может обернуть JSON в ```json ... ``` блоки
    text = result.strip()
    if text.startswith("```"):
        # Убираем ```json и ```
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

    # Ищем JSON-объект
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Gemini JSON parse error: {e}\ntext: {text[:300]}")
        return None


async def explain_topic(
    topic: str,
    subject: str,
    grade: int,
    level: str,
    user_id: int,
    student_subjects: list[str] | None = None,
) -> str:
    """Объясняет тему школьнику."""
    from templates.prompts import explain_topic_prompt
    prompt = explain_topic_prompt(topic, subject, grade, level, student_subjects)
    result = await call_gemini(prompt, user_id=user_id)
    return result or "Не удалось получить объяснение. Попробуй позже."


async def solve_task_with_gemini(
    task: str,
    wolfram_steps: str,
    grade: int,
    subject: str,
    user_id: int,
    student_subjects: list[str] | None = None,
) -> str:
    """Решает задачу с помощью Gemini (с или без шагов Wolfram)."""
    from templates.prompts import solve_task_prompt
    prompt = solve_task_prompt(task, wolfram_steps, grade, subject, student_subjects)
    result = await call_gemini(prompt, user_id=user_id, use_cache=True, cache_ttl=30)
    return result or "Не удалось получить решение. Попробуй позже."


async def analyze_homework_photo(image_data: bytes, image_mime: str, user_id: int) -> Optional[dict]:
    """Анализирует фото домашнего задания через Gemini Vision."""
    from templates.prompts import check_homework_photo_prompt
    prompt = check_homework_photo_prompt()
    result = await call_gemini_json(
        prompt=prompt,
        user_id=user_id,
        image_data=image_data,
        image_mime=image_mime,
        use_cache=False,  # Фото не кэшируем
    )
    return result


async def check_task_with_gemini(task_condition: str, student_answer: str,
                                   subject: str, grade: int, user_id: int,
                                   correct_answer: str = None) -> Optional[dict]:
    """Проверяет задание через Gemini (для гуманитарных или без Wolfram)."""
    from templates.prompts import check_homework_task_prompt
    prompt = check_homework_task_prompt(task_condition, student_answer, subject, grade, correct_answer)
    return await call_gemini_json(prompt, user_id=user_id, use_cache=False)


async def generate_diagnostic_questions(subject: str, grade: int, user_id: int) -> Optional[dict]:
    """Генерирует диагностические вопросы."""
    from templates.prompts import generate_diagnostic_prompt
    prompt = generate_diagnostic_prompt(subject, grade)
    return await call_gemini_json(prompt, user_id=user_id, use_cache=True, cache_ttl=7)


async def build_study_plan(subject: str, weak_topics: list[str], grade: int, user_id: int) -> Optional[dict]:
    """Составляет учебный план на основе слабых тем."""
    from templates.prompts import build_study_plan_prompt
    prompt = build_study_plan_prompt(subject, weak_topics, grade)
    return await call_gemini_json(prompt, user_id=user_id, use_cache=False)


async def generate_exam(subject: str, exam_type: str, grade: int, user_id: int) -> Optional[dict]:
    """Генерирует вариант экзамена."""
    from templates.prompts import generate_exam_prompt
    prompt = generate_exam_prompt(subject, exam_type, grade)
    return await call_gemini_json(prompt, user_id=user_id, use_cache=False)


async def grade_extended_answer(task_text: str, student_answer: str, criteria: str,
                                 subject: str, exam_type: str, user_id: int) -> Optional[dict]:
    """Проверяет развёрнутый ответ на экзамен."""
    from templates.prompts import grade_extended_answer_prompt
    prompt = grade_extended_answer_prompt(task_text, student_answer, criteria, subject, exam_type)
    return await call_gemini_json(prompt, user_id=user_id, use_cache=False)


async def get_progress_summary(student_name: str, stats: dict, user_id: int) -> str:
    """Генерирует резюме успеваемости для родителей."""
    from templates.prompts import progress_summary_prompt
    prompt = progress_summary_prompt(student_name, stats)
    result = await call_gemini(prompt, user_id=user_id, use_cache=False)
    return result or "Не удалось сформировать отчёт."


async def get_encyclopedia_entry(
    topic: str,
    mode: str,
    grade: int,
    level: str,
    user_id: int,
    previous_text: str | None = None,
) -> Optional[str]:
    """Генерирует энциклопедическую справку в выбранном формате."""
    from templates.prompts import encyclopedia_prompt
    prompt = encyclopedia_prompt(topic, mode, grade, level, previous_text)
    return await call_gemini(prompt, user_id=user_id, use_cache=True, cache_ttl=14)


async def generate_encyclopedia_quiz(
    topic: str,
    article_text: str,
    grade: int,
    user_id: int,
) -> Optional[dict]:
    """Генерирует мини-викторину по энциклопедической теме."""
    from templates.prompts import encyclopedia_quiz_prompt
    prompt = encyclopedia_quiz_prompt(topic, article_text, grade)
    return await call_gemini_json(prompt, user_id=user_id, use_cache=False)
