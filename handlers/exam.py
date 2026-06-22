"""
Хэндлер подготовки к экзаменам ОГЭ/ЕГЭ.
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
from config import EXAM_TYPES
from utils.helpers import match_subject, compare_answers
from keyboards import exam_subjects_keyboard, exam_type_keyboard, compact_keyboard, main_menu_keyboard

logger = logging.getLogger(__name__)
router = Router()


class ExamStates(StatesGroup):
    choosing_subject = State()
    choosing_type = State()
    solving = State()


@router.message(F.text == "🎓 Экзамен")
@router.message(Command("exam"))
async def start_exam(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    if not db.get_student(user_id):
        await message.answer("Сначала зарегистрируйся! Напиши /start")
        return

    args = message.text.split(maxsplit=2) if message.text else []
    subject_arg = args[1].strip() if len(args) > 1 else None
    type_arg = args[2].strip().upper() if len(args) > 2 else None

    if subject_arg and type_arg and type_arg in EXAM_TYPES:
        matched_subj = match_subject(subject_arg)
        if matched_subj:
            await _generate_exam(message, state, matched_subj, type_arg)
            return

    await message.answer(
        "🎓 <b>Пробный ОГЭ/ЕГЭ</b>\n\nВыбери предмет:",
        parse_mode="HTML",
        reply_markup=exam_subjects_keyboard(),
    )
    await state.set_state(ExamStates.choosing_subject)


@router.message(ExamStates.choosing_subject)
async def got_exam_subject(message: Message, state: FSMContext) -> None:
    subject = match_subject(message.text.strip())
    if not subject:
        await message.answer("Выбери предмет из списка:")
        return

    await state.update_data(subject=subject)
    await message.answer(
        f"Предмет: <b>{subject}</b>\nВыбери тип экзамена:",
        parse_mode="HTML",
        reply_markup=exam_type_keyboard(),
    )
    await state.set_state(ExamStates.choosing_type)


@router.message(ExamStates.choosing_type)
async def got_exam_type(message: Message, state: FSMContext) -> None:
    text = message.text.upper()
    if "ОГЭ" in text or "OGE" in text:
        exam_type = "OGE"
    elif "ЕГЭ" in text or "EGE" in text:
        exam_type = "EGE"
    else:
        await message.answer("Выбери: 📘 ОГЭ или 📗 ЕГЭ")
        return

    data = await state.get_data()
    await _generate_exam(message, state, data.get("subject", "Математика"), exam_type)


async def _generate_exam(message: Message, state: FSMContext, subject: str, exam_type: str) -> None:
    user_id = message.from_user.id
    grade = 9 if exam_type == "OGE" else 11

    loading = await message.answer(
        f"⚙️ Генерирую вариант {exam_type} по «{subject}»...\n"
        "Это займёт ~30 секунд.",
    )

    exam_data = await gemini_service.generate_exam(subject, exam_type, grade, user_id)

    if not exam_data or "tasks" not in exam_data:
        await loading.edit_text("❌ Не удалось сгенерировать вариант. Попробуй позже.")
        await state.clear()
        return

    tasks = exam_data["tasks"]
    db.save_exam_session(user_id, subject, exam_type, tasks)
    await loading.delete()

    exam_name = EXAM_TYPES.get(exam_type, exam_type)
    await message.answer(
        f"🎓 <b>{exam_name} по {subject}</b>\n"
        f"Заданий: {len(tasks)}\n\n"
        "📝 Инструкция:\n"
        "• Введи: <code>N: ответ</code> (например: <code>1: Б</code>)\n"
        "• Напиши <b>финиш</b> для завершения\n"
        "• Напиши <b>задание N</b> чтобы перечитать задание\n\n"
        "Удачи! 💪",
        parse_mode="HTML",
        reply_markup=compact_keyboard(),
    )

    await _send_exam_tasks(message, tasks)
    await state.set_state(ExamStates.solving)


async def _send_exam_tasks(message: Message, tasks: list) -> None:
    parts: dict[str, list] = {}
    for t in tasks:
        parts.setdefault(t.get("part", "A"), []).append(t)

    for part_name, part_tasks in sorted(parts.items()):
        lines = [f"\n📋 <b>Часть {part_name}</b>\n"]
        for t in part_tasks:
            n = t.get("number", "?")
            text = t.get("text", "")
            max_score = t.get("max_score", 1)
            lines.append(f"<b>Задание {n}</b> [{max_score} балл(ов)]")
            lines.append(text)
            if t.get("options"):
                for i, opt in enumerate(t["options"]):
                    letters = ["А", "Б", "В", "Г"]
                    lines.append(f"  {letters[i] if i < 4 else i+1}) {opt}")
            if t.get("type") == "extended" and t.get("criteria"):
                lines.append(f"<i>Критерии: {t['criteria'][:200]}</i>")
            lines.append("")

        full_text = "\n".join(lines)
        if len(full_text) > 4000:
            for t in part_tasks:
                n = t.get("number", "?")
                text = t.get("text", "")
                opts = t.get("options", [])
                opt_text = ""
                if opts:
                    letters = ["А", "Б", "В", "Г"]
                    opt_text = "\n" + "\n".join(
                        f"  {letters[i] if i < 4 else i+1}) {o}" for i, o in enumerate(opts)
                    )
                await message.answer(f"<b>Задание {n}</b>\n{text}{opt_text}", parse_mode="HTML")
        else:
            await message.answer(full_text, parse_mode="HTML")


@router.message(ExamStates.solving, F.text == "🏠 Меню")
async def exam_exit_menu(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    db.delete_exam_session(user_id)
    await state.clear()
    await message.answer("Экзамен прерван. Прогресс не сохранён.", reply_markup=main_menu_keyboard())


@router.message(ExamStates.solving)
async def process_exam_answer(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    text = message.text.strip()

    session = db.get_exam_session(user_id)
    if not session:
        await state.clear()
        return

    if text.lower() in ("финиш", "finish", "конец", "завершить", "⏹ стоп"):
        await _finish_exam(message, user_id)
        await state.clear()
        await message.answer("Экзамен завершён!", reply_markup=main_menu_keyboard())
        return

    if text.lower().startswith("задание"):
        try:
            n = int(text.split()[-1])
            tasks = json.loads(session["tasks"])
            task = next((t for t in tasks if t.get("number") == n), None)
            if task:
                await message.answer(f"<b>Задание {n}:</b>\n{task.get('text', '')}", parse_mode="HTML")
            else:
                await message.answer(f"Задание {n} не найдено.")
        except ValueError:
            await message.answer("Укажи номер задания: задание 5")
        return

    answers = json.loads(session["answers"])

    if ":" in text:
        parts = text.split(":", 1)
        try:
            task_num = int(parts[0].strip())
            answer_text = parts[1].strip()
            answers = [a for a in answers if a.get("number") != task_num]
            answers.append({"number": task_num, "answer": answer_text})
            db.update_exam_session(user_id, answers)
            await message.answer(f"✅ Ответ на задание {task_num} сохранён.")
        except ValueError:
            await message.answer("Неверный формат. Используй: <code>N: ответ</code>", parse_mode="HTML")
    else:
        await message.answer(
            "Используй формат: <code>N: ответ</code>\n"
            "Или напиши <b>финиш</b> для завершения.",
            parse_mode="HTML",
        )


async def _finish_exam(message: Message, user_id: int) -> None:
    session = db.get_exam_session(user_id)
    if not session:
        return

    tasks = json.loads(session["tasks"])
    answers_given = json.loads(session.get("answers", "[]"))
    subject = session["subject"]
    exam_type = session["exam_type"]
    answer_map = {a["number"]: a["answer"] for a in answers_given}

    loading = await message.answer("🔍 Проверяю ответы...")

    total_score = 0
    max_total = 0
    detailed = {}

    for task in tasks:
        n = task.get("number")
        correct = task.get("correct_answer", "")
        task_type = task.get("type", "short")
        max_score = task.get("max_score", 1)
        user_ans = answer_map.get(n, "")
        max_total += max_score

        if task_type == "extended" and task.get("criteria"):
            if user_ans:
                grade_result = await gemini_service.grade_extended_answer(
                    task_text=task.get("text", ""),
                    student_answer=user_ans,
                    criteria=task.get("criteria", ""),
                    subject=subject,
                    exam_type=exam_type,
                    user_id=user_id,
                )
                if grade_result:
                    score = grade_result.get("score", 0)
                    total_score += score
                    detailed[str(n)] = {
                        "score": score,
                        "max": max_score,
                        "feedback": grade_result.get("feedback", ""),
                    }
            else:
                detailed[str(n)] = {"score": 0, "max": max_score, "feedback": "Нет ответа"}
        else:
            is_correct = compare_answers(str(user_ans).lower(), str(correct).lower())
            score = max_score if is_correct else 0
            total_score += score
            detailed[str(n)] = {
                "score": score,
                "max": max_score,
                "correct_answer": correct,
                "user_answer": user_ans,
            }

    db.delete_exam_session(user_id)
    db.save_exam_result(user_id, subject, exam_type, total_score, max_total, detailed)

    pct = total_score / max_total * 100 if max_total > 0 else 0
    grade = _score_to_grade(pct, exam_type)

    await loading.delete()

    result_text = (
        f"🎓 <b>Результаты {EXAM_TYPES.get(exam_type, exam_type)} — {subject}</b>\n\n"
        f"Набрано: <b>{total_score}/{max_total}</b> баллов ({pct:.0f}%)\n"
        f"Оценка: <b>{grade}</b>\n\n"
    )

    wrong = [(n, d) for n, d in detailed.items() if d.get("score", 0) < d.get("max", 1)]
    if wrong:
        result_text += "❌ <b>Ошибки:</b>\n"
        for n, d in wrong[:10]:
            ca = d.get("correct_answer", "")
            ua = d.get("user_answer", "нет ответа")
            fb = d.get("feedback", "")
            if ca:
                result_text += f"  Задание {n}: «{ua}» → «{ca}»\n"
            elif fb:
                result_text += f"  Задание {n}: {fb[:100]}\n"

    result_text += "\n📈 Используй /stats для отслеживания прогресса"
    await message.answer(result_text, parse_mode="HTML")


def _score_to_grade(pct: float, exam_type: str) -> str:
    if exam_type == "EGE":
        score = int(pct)
        if score >= 90:
            return f"~{score} (отлично)"
        if score >= 70:
            return f"~{score} (хорошо)"
        if score >= 45:
            return f"~{score} (удовлетворительно)"
        return f"~{score} (не сдан)"
    if pct >= 85:
        return "5 (отлично)"
    if pct >= 65:
        return "4 (хорошо)"
    if pct >= 45:
        return "3 (удовлетворительно)"
    return "2 (не сдан)"
