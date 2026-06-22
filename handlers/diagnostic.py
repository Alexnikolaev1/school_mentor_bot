"""
Хэндлер диагностики пробелов в знаниях.
"""
import json
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from services import gemini_service
from utils.cache import get_diagnostic_cache, set_diagnostic_cache
from utils.helpers import match_subject, compare_answers
from keyboards import subjects_keyboard, compact_keyboard, main_menu_keyboard

logger = logging.getLogger(__name__)
router = Router()


class DiagnosticStates(StatesGroup):
    choosing_subject = State()
    answering = State()


@router.message(F.text == "📊 Диагностика")
@router.message(Command("diagnostic"))
async def start_diagnostic(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    if not db.get_student(user_id):
        await message.answer("Сначала зарегистрируйся! Напиши /start")
        return

    args = message.text.split(maxsplit=1)
    subject_arg = args[1].strip() if len(args) > 1 else None

    if subject_arg:
        matched = match_subject(subject_arg)
        if matched:
            await _begin_diagnostic(message, state, matched)
            return

    await message.answer(
        "📊 <b>Диагностика знаний</b>\n\nВыбери предмет для проверки:",
        parse_mode="HTML",
        reply_markup=subjects_keyboard(),
    )
    await state.set_state(DiagnosticStates.choosing_subject)


@router.message(DiagnosticStates.choosing_subject)
async def got_diagnostic_subject(message: Message, state: FSMContext) -> None:
    subject = match_subject(message.text.strip())
    if not subject:
        await message.answer("Выбери предмет из списка:")
        return
    await _begin_diagnostic(message, state, subject)


async def _begin_diagnostic(message: Message, state: FSMContext, subject: str) -> None:
    user_id = message.from_user.id
    student = db.get_student(user_id)
    grade = student.get("grade", 9) if student else 9

    questions = get_diagnostic_cache(subject, grade)

    if not questions:
        loading_msg = await message.answer(
            f"📊 Генерирую тест по предмету «{subject}» для {grade} класса...",
        )
        result = await gemini_service.generate_diagnostic_questions(subject, grade, user_id)

        if not result or "questions" not in result:
            await loading_msg.edit_text("❌ Не удалось создать тест. Попробуй позже.")
            await state.clear()
            return

        questions = result["questions"]
        set_diagnostic_cache(subject, grade, questions)
        await loading_msg.delete()

    db.save_diagnostic_session(user_id, subject, questions)

    await message.answer(
        f"📊 <b>Диагностика: {subject}</b>\n"
        f"Класс: {grade} | Вопросов: {len(questions)}\n\n"
        "Отвечай кратко. Напиши <b>стоп</b> чтобы закончить досрочно.\n\n"
        "─── Начинаем! ───",
        parse_mode="HTML",
        reply_markup=compact_keyboard(),
    )

    await state.set_state(DiagnosticStates.answering)
    await _send_next_question(message, user_id)


async def _send_next_question(message: Message, user_id: int) -> None:
    session = db.get_diagnostic_session(user_id)
    if not session:
        return

    questions = json.loads(session["questions"])
    current_q = session["current_q"]

    if current_q >= len(questions):
        await _finish_diagnostic(message, user_id)
        return

    q = questions[current_q]
    difficulty_stars = "⭐" * q.get("difficulty", 1)

    await message.answer(
        f"<b>Вопрос {current_q + 1}/{len(questions)}</b> {difficulty_stars}\n"
        f"📌 Тема: {q.get('topic', '')}\n\n"
        f"{q.get('text', '')}",
        parse_mode="HTML",
    )


@router.message(DiagnosticStates.answering, F.text == "🏠 Меню")
async def diagnostic_exit_menu(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    db.delete_diagnostic_session(user_id)
    await state.clear()
    await message.answer("Диагностика прервана.", reply_markup=main_menu_keyboard())


@router.message(DiagnosticStates.answering)
async def got_diagnostic_answer(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    text = message.text.strip().lower()

    if text in ("стоп", "stop", "отмена", "выход", "⏹ стоп"):
        await _finish_diagnostic(message, user_id)
        await state.clear()
        await message.answer("Диагностика завершена.", reply_markup=main_menu_keyboard())
        return

    session = db.get_diagnostic_session(user_id)
    if not session:
        await state.clear()
        return

    questions = json.loads(session["questions"])
    current_q = session["current_q"]
    answers = json.loads(session["answers"])

    if current_q >= len(questions):
        await _finish_diagnostic(message, user_id)
        await state.clear()
        return

    q = questions[current_q]
    is_correct = compare_answers(message.text.strip(), q.get("correct_answer", ""))

    answers.append({
        "question_idx": current_q,
        "user_answer": message.text.strip(),
        "correct_answer": q.get("correct_answer", ""),
        "correct": is_correct,
        "topic": q.get("topic", ""),
        "difficulty": q.get("difficulty", 1),
    })

    feedback = (
        "✅ Правильно!"
        if is_correct
        else (
            f"❌ Ошибка.\n"
            f"Правильный ответ: <b>{q.get('correct_answer', '?')}</b>\n"
            f"💬 {q.get('explanation', '')}"
        )
    )
    await message.answer(feedback, parse_mode="HTML")

    next_q = current_q + 1
    db.update_diagnostic_session(user_id, next_q, answers)

    if next_q >= len(questions):
        await _finish_diagnostic(message, user_id)
        await state.clear()
        await message.answer("Тест завершён!", reply_markup=main_menu_keyboard())
    else:
        await _send_next_question(message, user_id)


async def _finish_diagnostic(message: Message, user_id: int) -> None:
    session = db.get_diagnostic_session(user_id)
    if not session:
        return

    answers = json.loads(session.get("answers", "[]"))
    subject = session["subject"]
    student = db.get_student(user_id)
    grade = student.get("grade", 9) if student else 9

    db.delete_diagnostic_session(user_id)

    if not answers:
        await message.answer("Диагностика завершена без ответов.")
        return

    topics_stats: dict[str, dict] = {}
    for ans in answers:
        topic = ans.get("topic", "Общее")
        if topic not in topics_stats:
            topics_stats[topic] = {"correct": 0, "total": 0}
        topics_stats[topic]["total"] += 1
        if ans.get("correct"):
            topics_stats[topic]["correct"] += 1

    total_correct = sum(v["correct"] for v in topics_stats.values())
    total_qs = len(answers)
    pct = total_correct / total_qs * 100 if total_qs else 0

    lines = [
        f"📊 <b>Результаты диагностики — {subject}</b>\n",
        f"Правильных ответов: {total_correct}/{total_qs} ({pct:.0f}%)\n",
        "─── По темам ───",
    ]

    weak_topics = []
    for topic, stats in topics_stats.items():
        t_pct = stats["correct"] / stats["total"] * 100
        icon = "✅" if t_pct >= 70 else "⚠️" if t_pct >= 40 else "❌"
        lines.append(f"{icon} {topic}: {stats['correct']}/{stats['total']} ({t_pct:.0f}%)")
        if t_pct < 70:
            weak_topics.append(topic)

    await message.answer("\n".join(lines), parse_mode="HTML")

    if not weak_topics:
        await message.answer("🌟 Отлично! Серьёзных пробелов не выявлено.")
        return

    plan_msg = await message.answer("📋 Составляю персональный учебный план...")

    plan_result = await gemini_service.build_study_plan(
        subject=subject,
        weak_topics=weak_topics,
        grade=grade,
        user_id=user_id,
    )

    if plan_result and "plan" in plan_result:
        plans = [
            {"subject": subject, "topic": p["topic"], "priority": p.get("priority", 2)}
            for p in plan_result["plan"]
        ]
        db.save_study_plan(user_id, plans)

        plan_lines = [f"\n📋 <b>Учебный план по {subject}:</b>\n"]
        for p in plan_result["plan"][:6]:
            priority_icon = {1: "🔴", 2: "🟡", 3: "🟢"}.get(p.get("priority", 2), "🔵")
            plan_lines.append(
                f"{priority_icon} <b>{p['topic']}</b>\n"
                f"   {p.get('micro_lesson', p.get('reason', ''))}"
            )

        plan_lines.append("\nИспользуй /stats и /done для отслеживания прогресса")
        await plan_msg.edit_text("\n".join(plan_lines), parse_mode="HTML")
    else:
        await plan_msg.edit_text("Не удалось составить план. Обратись за помощью вручную.")
