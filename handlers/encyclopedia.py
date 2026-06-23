"""
Энциклопедические знания — структурированные справки и закрепление материала.
"""
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from services import gemini_service
from services.tts import text_to_speech, delete_tts_file
from keyboards import (
    main_menu_keyboard,
    encyclopedia_mode_keyboard,
    encyclopedia_followup_keyboard,
    encyclopedia_quiz_keyboard,
)
from keyboards.menus import ENCYCLOPEDIA_MODE_BUTTONS, ENCYCLOPEDIA_FOLLOWUP_BUTTONS
from templates.prompts import ENCYCLOPEDIA_MODE_LABELS
from utils.helpers import compare_answers
from utils.text import send_long_message

logger = logging.getLogger(__name__)
router = Router()

MODE_BY_BUTTON = {
    "📌 Краткий справочник": "brief",
    "📚 Полная статья": "article",
    "🕐 Хронология": "timeline",
    "🔗 Карта связей": "connections",
}


class EncyclopediaStates(StatesGroup):
    choosing_mode = State()
    waiting_topic = State()
    followup = State()
    quiz_answering = State()


@router.message(F.text == "📖 Энциклопедические знания")
@router.message(Command("encyclopedia"))
async def start_encyclopedia(message: Message, state: FSMContext) -> None:
    if not db.get_student(message.from_user.id):
        await message.answer("Сначала зарегистрируйся! Напиши /start")
        return

    await message.answer(
        "📖 <b>Энциклопедические знания</b>\n\n"
        "Здесь ты получишь структурированные справки — как в умной энциклопедии, "
        "но под твой класс.\n\n"
        "<b>Как пользоваться:</b>\n"
        "1️⃣ Выбери формат материала\n"
        "2️⃣ Напиши тему (например: <i>Древний Рим</i>, <i>фотосинтез</i>, <i>Чехов</i>)\n"
        "3️⃣ После справки — углубись, пройди мини-викторину или послушай вслух\n\n"
        "Выбери формат 👇",
        parse_mode="HTML",
        reply_markup=encyclopedia_mode_keyboard(),
    )
    await state.set_state(EncyclopediaStates.choosing_mode)


@router.message(EncyclopediaStates.choosing_mode, F.text == "◀️ Меню")
@router.message(EncyclopediaStates.waiting_topic, F.text == "◀️ Меню")
@router.message(EncyclopediaStates.followup, F.text == "◀️ Меню")
@router.message(EncyclopediaStates.quiz_answering, F.text.in_({"◀️ Меню", "⏹ Стоп"}))
async def encyclopedia_exit(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard())


@router.message(EncyclopediaStates.choosing_mode)
async def chose_mode(message: Message, state: FSMContext) -> None:
    mode = MODE_BY_BUTTON.get(message.text.strip())
    if not mode:
        await message.answer("Выбери формат из списка 👇", reply_markup=encyclopedia_mode_keyboard())
        return

    await state.update_data(mode=mode)
    label = ENCYCLOPEDIA_MODE_LABELS.get(mode, mode)
    await message.answer(
        f"Формат: <b>{label}</b>\n\n"
        "Напиши тему или вопрос:\n"
        "• <i>Вторая мировая война</i>\n"
        "• <i>Кто такой Пушкин</i>\n"
        "• <i>Что такое гравитация</i>",
        parse_mode="HTML",
    )
    await state.set_state(EncyclopediaStates.waiting_topic)


@router.message(EncyclopediaStates.waiting_topic, F.text)
async def got_topic(message: Message, state: FSMContext) -> None:
    topic = message.text.strip()
    if len(topic) < 2:
        await message.answer("Тема слишком короткая. Напиши подробнее:")
        return

    data = await state.get_data()
    mode = data.get("mode", "brief")
    await _generate_and_show(message, state, topic, mode)


@router.message(EncyclopediaStates.followup)
async def handle_followup(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    data = await state.get_data()
    topic = data.get("topic", "")
    last_text = data.get("last_text", "")

    if text == "📖 Новая тема":
        await start_encyclopedia(message, state)
        return

    if text == "📚 Углубить":
        await _generate_and_show(message, state, topic, "deepen", previous_text=last_text)
        return

    if text == "🔗 Связанные темы":
        await _generate_and_show(message, state, topic, "connections", previous_text=last_text)
        return

    if text == "🎯 Проверить знания":
        await _start_quiz(message, state)
        return

    if text == "🔊 Озвучить":
        await _send_tts(message, last_text)
        return

    if text in ENCYCLOPEDIA_FOLLOWUP_BUTTONS or text in ENCYCLOPEDIA_MODE_BUTTONS:
        await message.answer("Используй кнопки ниже 👇", reply_markup=encyclopedia_followup_keyboard())
        return

    # Свободный текст в режиме followup — новый запрос в том же формате
    await _generate_and_show(message, state, text, data.get("mode", "brief"))


@router.message(EncyclopediaStates.quiz_answering)
async def quiz_answer(message: Message, state: FSMContext) -> None:
    if message.text.strip().lower() in ("стоп", "⏹ стоп"):
        await state.set_state(EncyclopediaStates.followup)
        await message.answer("Викторина прервана.", reply_markup=encyclopedia_followup_keyboard())
        return

    data = await state.get_data()
    questions = data.get("quiz_questions", [])
    current = data.get("quiz_index", 0)
    answers = data.get("quiz_answers", [])

    if current >= len(questions):
        await _finish_quiz(message, state)
        return

    q = questions[current]
    is_correct = compare_answers(message.text.strip(), q.get("correct_answer", ""))
    answers.append(is_correct)

    feedback = (
        "✅ Верно!"
        if is_correct
        else f"❌ Неверно. Правильно: <b>{q.get('correct_answer', '?')}</b>\n💬 {q.get('explanation', '')}"
    )
    await message.answer(feedback, parse_mode="HTML")

    next_idx = current + 1
    await state.update_data(quiz_index=next_idx, quiz_answers=answers)

    if next_idx >= len(questions):
        await _finish_quiz(message, state)
    else:
        await _send_quiz_question(message, questions[next_idx], next_idx + 1, len(questions))


async def _generate_and_show(
    message: Message,
    state: FSMContext,
    topic: str,
    mode: str,
    previous_text: str | None = None,
) -> None:
    user_id = message.from_user.id
    student = db.get_student(user_id)
    grade = student.get("grade", 9) if student else 9
    level = student.get("level", "intermediate") if student else "intermediate"

    label = ENCYCLOPEDIA_MODE_LABELS.get(mode, mode)
    loading = await message.answer(f"📖 Готовлю «{label}» по теме «{topic}»...")

    response = await gemini_service.get_encyclopedia_entry(
        topic=topic,
        mode=mode,
        grade=grade,
        level=level,
        user_id=user_id,
        previous_text=previous_text,
    )

    await loading.delete()

    if not response:
        await message.answer("Не удалось получить справку. Попробуй другую формулировку.")
        return

    header = f"📖 <b>{label}</b> — <i>{topic}</i>\n\n"
    await send_long_message(message, header + response)

    db.save_last_response(user_id, response)
    await state.update_data(topic=topic, mode=mode, last_text=response)
    await state.set_state(EncyclopediaStates.followup)

    await message.answer(
        "Что дальше?\n"
        "• <b>Углубить</b> — больше деталей\n"
        "• <b>Связанные темы</b> — карта знаний\n"
        "• <b>Проверить знания</b> — мини-викторина из 3 вопросов\n"
        "• <b>Озвучить</b> — прослушать справку",
        parse_mode="HTML",
        reply_markup=encyclopedia_followup_keyboard(),
    )


async def _start_quiz(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    topic = data.get("topic", "")
    last_text = data.get("last_text", "")

    if not last_text:
        await message.answer("Сначала получи справку по теме.")
        return

    student = db.get_student(message.from_user.id)
    grade = student.get("grade", 9) if student else 9

    loading = await message.answer("🎯 Составляю викторину...")
    result = await gemini_service.generate_encyclopedia_quiz(topic, last_text, grade, message.from_user.id)
    await loading.delete()

    if not result or not result.get("questions"):
        await message.answer("Не удалось создать викторину. Попробуй позже.")
        return

    questions = result["questions"][:3]
    await state.update_data(quiz_questions=questions, quiz_index=0, quiz_answers=[])
    await state.set_state(EncyclopediaStates.quiz_answering)

    await message.answer(
        f"🎯 <b>Мини-викторина: {topic}</b>\n"
        f"Вопросов: {len(questions)}. Отвечай кратко.\n"
        "Напиши <b>стоп</b> чтобы прервать.",
        parse_mode="HTML",
        reply_markup=encyclopedia_quiz_keyboard(),
    )
    await _send_quiz_question(message, questions[0], 1, len(questions))


async def _send_quiz_question(message: Message, question: dict, num: int, total: int) -> None:
    await message.answer(
        f"<b>Вопрос {num}/{total}</b>\n\n{question.get('text', '')}",
        parse_mode="HTML",
    )


async def _finish_quiz(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    answers = data.get("quiz_answers", [])
    correct = sum(1 for a in answers if a)
    total = len(answers)

    if total == 0:
        await state.set_state(EncyclopediaStates.followup)
        return

    pct = correct / total * 100
    if pct >= 100:
        comment = "🌟 Отлично! Энциклопедические знания закреплены."
    elif pct >= 66:
        comment = "👍 Хорошо! Перечитай справку и попробуй ещё раз."
    else:
        comment = "📚 Стоит повторить материал — нажми «Углубить» или «Озвучить»."

    await message.answer(
        f"🎯 <b>Результат викторины:</b> {correct}/{total}\n{comment}",
        parse_mode="HTML",
        reply_markup=encyclopedia_followup_keyboard(),
    )
    await state.set_state(EncyclopediaStates.followup)


async def _send_tts(message: Message, text: str) -> None:
    if not text:
        await message.answer("Нет текста для озвучки.")
        return

    status = await message.answer("🎙️ Синтезирую речь...")
    filepath = await text_to_speech(text)

    if filepath:
        try:
            await message.answer_voice(FSInputFile(filepath))
        except Exception as e:
            logger.error(f"Encyclopedia TTS: {e}")
            await message.answer("Не удалось отправить голосовое.")
        finally:
            delete_tts_file(filepath)
    else:
        await message.answer("Озвучка временно недоступна.")

    await status.delete()
