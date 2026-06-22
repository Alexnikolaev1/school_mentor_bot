"""
Хэндлер для объяснения тем и решения задач.
Использует Wolfram Alpha + Gemini.
"""
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from services import gemini_service, wolfram_service
from services.tts import text_to_speech, delete_tts_file
from utils.helpers import (
    is_math_task, get_subject_from_text, is_menu_button, parse_student_subjects,
)
from utils.text import send_long_message

logger = logging.getLogger(__name__)
router = Router()


class ExplainStates(StatesGroup):
    waiting_topic = State()
    waiting_tts_confirm = State()


@router.message(F.text == "📚 Объяснить тему")
async def ask_for_topic(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    if not db.get_student(user_id):
        await message.answer("Сначала зарегистрируйся! Напиши /start")
        return

    await message.answer(
        "💡 Напиши тему или задачу, и я объясню!\n\n"
        "Примеры:\n"
        "• Объясни что такое логарифмы\n"
        "• Реши уравнение 3x + 5 = 20\n"
        "• Что такое фотосинтез?\n\n"
        "Можешь отправить голосовое сообщение 🎤"
    )
    await state.set_state(ExplainStates.waiting_topic)


@router.message(ExplainStates.waiting_topic, F.text)
async def process_topic_request(message: Message, state: FSMContext) -> None:
    await state.clear()
    await process_text_question(message, message.text.strip())


@router.message(
    F.text,
    ~F.text.startswith("/"),
)
async def free_text_question(message: Message, state: FSMContext) -> None:
    """Свободный текст — маршрутизируем в объяснение, если не кнопка меню."""
    if await state.get_state():
        return

    text = message.text.strip()
    if not text or is_menu_button(text):
        return

    user_id = message.from_user.id
    if not db.get_student(user_id):
        return

    await process_text_question(message, text)


async def process_text_question(message: Message, text: str) -> None:
    """Публичная функция — вызывается из voice.py после транскрибации."""
    user_id = message.from_user.id
    student = db.get_student(user_id)
    if not student:
        await message.answer("Сначала зарегистрируйся! Напиши /start")
        return

    grade = student.get("grade", 9)
    level = student.get("level", "intermediate")
    subjects = parse_student_subjects(student.get("subjects", "[]"))

    if is_math_task(text):
        await _handle_math_task(message, text, grade, level, user_id, subjects)
    else:
        await _handle_topic_explanation(message, text, grade, level, user_id, subjects)


async def _handle_math_task(
    message: Message,
    text: str,
    grade: int,
    level: str,
    user_id: int,
    subjects: list[str],
) -> None:
    subject = get_subject_from_text(text)
    processing_msg = await message.answer("⚙️ Решаю задачу через Wolfram Alpha + Gemini...")

    short_answer, steps = await wolfram_service.solve_math_query(text)
    wolfram_worked = bool(short_answer or steps)

    response = await gemini_service.solve_task_with_gemini(
        task=text,
        wolfram_steps=steps or "",
        grade=grade,
        subject=subject,
        user_id=user_id,
        student_subjects=subjects,
    )
    prefix = (
        "🧮 <b>Решение:</b>\n\n"
        if wolfram_worked
        else "🧮 <b>Решение</b> (от AI, может содержать погрешности):\n\n"
    )

    await processing_msg.delete()

    if response:
        await send_long_message(message, prefix + response)
        db.save_last_response(user_id, response)
        if len(response) > 500:
            await message.answer(
                "🔊 Хочешь прослушать объяснение? Напиши <b>да</b>",
                parse_mode="HTML",
            )
    else:
        await message.answer("Не удалось решить задачу. Попробуй сформулировать иначе.")


async def _handle_topic_explanation(
    message: Message,
    text: str,
    grade: int,
    level: str,
    user_id: int,
    subjects: list[str],
) -> None:
    subject = get_subject_from_text(text)
    processing_msg = await message.answer("📚 Готовлю объяснение...")

    response = await gemini_service.explain_topic(
        topic=text,
        subject=subject,
        grade=grade,
        level=level,
        user_id=user_id,
        student_subjects=subjects,
    )

    await processing_msg.delete()

    if response:
        await send_long_message(message, f"💡 <b>Объяснение:</b>\n\n{response}")
        db.save_last_response(user_id, response)

        topic_id = db.get_active_topic_id(user_id)
        if topic_id:
            db.complete_study_topic(topic_id)
            db.set_active_topic(user_id, 0)

        if len(response) > 500:
            await message.answer(
                "🔊 Хочешь прослушать объяснение? Напиши <b>да</b>",
                parse_mode="HTML",
            )
    else:
        await message.answer("Не удалось получить объяснение. Попробуй позже.")


@router.message(F.text.lower() == "да")
async def handle_tts_request(message: Message, state: FSMContext) -> None:
    """Озвучивает последнее объяснение."""
    if await state.get_state():
        return

    user_id = message.from_user.id
    if db.get_diagnostic_session(user_id) or db.get_exam_session(user_id):
        return

    last_text = db.get_last_response(user_id)

    if not last_text:
        await message.answer(
            "Сначала задай вопрос — я сохраню ответ и смогу его озвучить 🔊"
        )
        return

    await state.clear()
    await _send_voice_response(message, last_text)


@router.message(Command("done"))
async def complete_current_topic(message: Message) -> None:
    """Отмечает текущую тему учебного плана как выполненную."""
    user_id = message.from_user.id
    topic_id = db.get_active_topic_id(user_id)
    if topic_id:
        db.complete_study_topic(topic_id)
        db.set_active_topic(user_id, 0)
        await message.answer("✅ Тема отмечена как выполненная! Так держать!")
    else:
        plan = db.get_study_plan(user_id)
        if plan:
            await message.answer(
                f"📋 Следующая тема: <b>{plan[0]['topic']}</b> ({plan[0]['subject']})\n"
                "Изучи её и напиши /done",
                parse_mode="HTML",
            )
        else:
            await message.answer("Учебный план пуст. Пройди /diagnostic для составления плана.")


@router.message(Command("voice_answer"))
async def voice_answer_cmd(message: Message) -> None:
    text = message.text.replace("/voice_answer", "").strip()
    if not text:
        await message.answer("Укажи текст: /voice_answer Текст для озвучки")
        return
    await _send_voice_response(message, text)


async def _send_voice_response(message: Message, text: str) -> None:
    status = await message.answer("🎙️ Синтезирую речь...")
    filepath = await text_to_speech(text)

    if filepath:
        try:
            await message.answer_voice(FSInputFile(filepath))
        except Exception as e:
            logger.error(f"TTS отправка: {e}")
            await message.answer("Не удалось отправить голосовое сообщение.")
        finally:
            delete_tts_file(filepath)
    else:
        await message.answer("Озвучка временно недоступна.")

    await status.delete()
