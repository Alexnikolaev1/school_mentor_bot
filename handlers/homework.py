"""
Хэндлер проверки домашнего задания по фото.
"""
import logging

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from services import gemini_service, wolfram_service
from keyboards import homework_subjects_keyboard, main_menu_keyboard
from utils.text import send_long_message

logger = logging.getLogger(__name__)
router = Router()


class HomeworkStates(StatesGroup):
    waiting_photo = State()
    waiting_subject = State()


@router.message(F.text == "📝 Проверить ДЗ")
async def start_homework_check(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    if not db.get_student(user_id):
        await message.answer("Сначала зарегистрируйся! Напиши /start")
        return

    await message.answer(
        "📝 <b>Проверка домашнего задания</b>\n\nСначала выбери предмет:",
        parse_mode="HTML",
        reply_markup=homework_subjects_keyboard(),
    )
    await state.set_state(HomeworkStates.waiting_subject)


@router.message(HomeworkStates.waiting_subject)
async def got_subject(message: Message, state: FSMContext) -> None:
    subject = message.text.strip()
    await state.update_data(subject=subject)
    await message.answer(
        f"📸 Отлично! Теперь отправь <b>фото</b> страницы с заданиями.\n\n"
        f"Предмет: {subject}\n\n"
        "💡 Советы: хорошее освещение, все задания в кадре, без размытия",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
    await state.set_state(HomeworkStates.waiting_photo)


@router.message(HomeworkStates.waiting_photo, F.photo)
async def process_homework_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    subject = data.get("subject", "Математика")
    await state.clear()

    user_id = message.from_user.id
    student = db.get_student(user_id)
    if not student:
        await message.answer("Сначала зарегистрируйся!")
        return

    grade = student.get("grade", 9)
    processing_msg = await message.answer("🔍 Анализирую домашнее задание...")

    photo = message.photo[-1]
    try:
        file = await message.bot.get_file(photo.file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        image_data = file_bytes.read() if hasattr(file_bytes, "read") else bytes(file_bytes)
    except Exception as e:
        logger.error(f"Ошибка скачивания фото: {e}")
        await processing_msg.edit_text("❌ Не удалось загрузить фото. Попробуй ещё раз.")
        return

    recognized = await gemini_service.analyze_homework_photo(
        image_data=image_data,
        image_mime="image/jpeg",
        user_id=user_id,
    )

    if not recognized:
        await processing_msg.edit_text("❌ Не удалось распознать задания. Попробуй более чёткое фото.")
        return

    if recognized.get("image_quality") == "blurry":
        await processing_msg.edit_text("📷 Фото нечёткое. Пересними при хорошем освещении.")
        return

    tasks = recognized.get("tasks", [])
    if not tasks:
        await processing_msg.edit_text("🤔 Не удалось найти задания на фото.")
        return

    await processing_msg.edit_text(f"✅ Распознал {len(tasks)} задани(я/й). Проверяю ответы...")

    results = []
    for task in tasks:
        result = await _check_single_task(task, subject, grade, user_id)
        results.append(result)
        db.log_homework(
            student_id=user_id,
            subject=subject,
            task_number=task.get("number", "?"),
            correct=result["correct"],
            max_score=1,
        )

    await processing_msg.delete()
    await send_long_message(message, _format_homework_results(results, subject))


async def _check_single_task(task: dict, subject: str, grade: int, user_id: int) -> dict:
    task_number = task.get("number", "?")
    condition = task.get("condition", "")
    student_answer = task.get("student_answer", "не указан")
    task_type = task.get("type", "math")

    result = {
        "number": task_number,
        "condition": condition[:100],
        "student_answer": student_answer,
        "correct": False,
        "correct_answer": None,
        "explanation": "",
    }

    if wolfram_service.is_math_task_type(task_type) and condition:
        short_answer, _ = await wolfram_service.solve_math_query(condition)
        if short_answer:
            result["correct_answer"] = short_answer
            check = await gemini_service.check_task_with_gemini(
                task_condition=condition,
                student_answer=student_answer,
                subject=subject,
                grade=grade,
                user_id=user_id,
                correct_answer=short_answer,
            )
            if check:
                result["correct"] = check.get("correct", False)
                result["explanation"] = check.get("explanation", "")
            return result

    check = await gemini_service.check_task_with_gemini(
        task_condition=condition,
        student_answer=student_answer,
        subject=subject,
        grade=grade,
        user_id=user_id,
    )
    if check:
        result["correct"] = check.get("correct", False)
        result["explanation"] = check.get("explanation", "")

    return result


def _format_homework_results(results: list[dict], subject: str) -> str:
    total = len(results)
    correct_count = sum(1 for r in results if r["correct"])

    lines = [
        f"📝 <b>Проверка домашнего задания — {subject}</b>\n",
        f"Правильно: {correct_count}/{total}\n",
        "─" * 30,
    ]

    for r in results:
        icon = "✅" if r["correct"] else "❌"
        cond_short = r["condition"][:60] + "..." if len(r["condition"]) > 60 else r["condition"]
        lines.append(f"\n{icon} <b>Задание {r['number']}</b>")
        if cond_short:
            lines.append(f"   <i>{cond_short}</i>")
        if r["student_answer"] and r["student_answer"] != "не указан":
            lines.append(f"   Твой ответ: {r['student_answer']}")
        if not r["correct"]:
            if r.get("correct_answer"):
                lines.append(f"   Правильный ответ: <b>{r['correct_answer']}</b>")
            if r.get("explanation"):
                lines.append(f"   💬 {r['explanation']}")
        else:
            lines.append("   Отличная работа!")

    pct = correct_count / total * 100 if total > 0 else 0
    if pct >= 80:
        lines.append(f"\n🌟 Великолепно! {pct:.0f}% — ты молодец!")
    elif pct >= 60:
        lines.append(f"\n👍 Хорошая работа! Есть что подтянуть ({pct:.0f}%)")
    else:
        lines.append(f"\n📚 Нужно повторить материал ({pct:.0f}%). Воспользуйся /diagnostic")

    return "\n".join(lines)


@router.message(HomeworkStates.waiting_photo, ~F.photo)
async def wrong_content_type(message: Message) -> None:
    await message.answer(
        "📸 Нужно именно <b>фото</b> тетради (не документ, не текст).",
        parse_mode="HTML",
    )
