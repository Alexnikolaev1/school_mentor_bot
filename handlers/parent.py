"""
Хэндлер родительского кабинета.
"""
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile

import database as db
from services.gemini_service import get_progress_summary
from utils.graph import build_progress_chart, build_subject_pie, aggregate_weekly_stats
from utils.helpers import progress_bar

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("invite"))
async def cmd_invite(message: Message) -> None:
    user_id = message.from_user.id
    if not db.get_student(user_id):
        await message.answer("Эта команда только для учеников.")
        return

    code = db.create_invite_code(user_id)

    await message.answer(
        "🔗 <b>Код приглашения для родителя:</b>\n\n"
        f"<code>{code}</code>\n\n"
        "Передай этот код родителю. Он напишет боту:\n"
        f"<code>/parent {code}</code>\n\n"
        "⏰ Код действует 24 часа, одноразовый.",
        parse_mode="HTML",
    )


@router.message(Command("parent"))
async def cmd_parent(message: Message) -> None:
    args = message.text.split(maxsplit=1)
    user_id = message.from_user.id

    if len(args) < 2:
        await message.answer(
            "Использование: <code>/parent КОД_ПРИГЛАШЕНИЯ</code>",
            parse_mode="HTML",
        )
        return

    code = args[1].strip().upper()
    student_id = db.get_student_by_invite(code)

    if not student_id:
        await message.answer("❌ Код не найден или истёк. Попроси новый код через /invite.")
        return

    if db.get_student(user_id):
        await message.answer("❌ Ты зарегистрирован как ученик, не как родитель.")
        return

    name = message.from_user.first_name or "Родитель"
    if not db.get_parent(user_id):
        db.upsert_parent(user_id, name)

    db.link_parent_student(user_id, student_id)
    db.mark_invite_used(code)

    student = db.get_student(student_id)
    student_name = student.get("name", "ученик") if student else "ученик"

    await message.answer(
        f"✅ Успешно! Ты теперь видишь успеваемость {student_name}.\n\n"
        "Команды:\n/progress — отчёт\n/progress_chart — график",
        parse_mode="HTML",
    )


@router.message(Command("progress"))
async def cmd_progress(message: Message) -> None:
    user_id = message.from_user.id
    if not db.get_parent(user_id):
        await message.answer("Эта команда для родителей. Зарегистрируйся через /start.")
        return

    students = db.get_linked_students(user_id)
    if not students:
        await message.answer("Ни один ученик не привязан. Используй /parent КОД")
        return

    loading = await message.answer("📊 Формирую отчёт...")
    for student in students:
        await _send_student_report(message, student, user_id)
    await loading.delete()


@router.message(Command("progress_chart"))
async def cmd_progress_chart(message: Message) -> None:
    """Отправляет только графики успеваемости."""
    user_id = message.from_user.id
    if not db.get_parent(user_id):
        await message.answer("Эта команда для родителей.")
        return

    students = db.get_linked_students(user_id)
    if not students:
        await message.answer("Ни один ученик не привязан.")
        return

    for student in students:
        await _send_progress_chart(message, student["user_id"], student.get("name", "Ученик"))
        await _send_subject_pie(message, student["user_id"], student.get("name", "Ученик"))


async def _send_student_report(message: Message, student: dict, parent_id: int) -> None:
    student_id = student["user_id"]
    student_name = student.get("name", "Ученик")

    stats_7 = db.get_homework_stats(student_id, days=7)
    stats_30 = db.get_homework_stats(student_id, days=30)
    exams = db.get_exam_results(student_id, limit=5)

    subjects_perf = {}
    for s in stats_30:
        total = s.get("total", 0)
        correct = s.get("correct_count", 0)
        if total > 0:
            subjects_perf[s["subject"]] = round(correct / total * 100, 1)

    tasks_week = sum(s.get("total", 0) for s in stats_7)
    tasks_month = sum(s.get("total", 0) for s in stats_30)

    stats_for_gemini = {
        "tasks_week": tasks_week,
        "tasks_month": tasks_month,
        "subjects": subjects_perf,
        "last_exams": [
            {"subject": e["subject"], "type": e["exam_type"], "score": f"{e['score']}/{e['max_score']}"}
            for e in exams[:3]
        ],
    }

    summary = await get_progress_summary(student_name, stats_for_gemini, parent_id)

    report_lines = [
        f"📊 <b>Отчёт об успеваемости</b>\n👤 {student_name} | {student.get('grade', '?')} класс\n",
        f"📅 <b>Активность:</b>",
        f"  • За неделю: {tasks_week} задач",
        f"  • За месяц: {tasks_month} задач",
    ]

    if subjects_perf:
        report_lines.append("\n📚 <b>Успеваемость по предметам (за месяц):</b>")
        for subj, pct in sorted(subjects_perf.items(), key=lambda x: -x[1]):
            report_lines.append(f"  {subj}: {progress_bar(pct)} {pct}%")

    if exams:
        report_lines.append("\n🎓 <b>Последние экзамены:</b>")
        for e in exams[:3]:
            pct = round(e["score"] / e["max_score"] * 100) if e["max_score"] else 0
            report_lines.append(
                f"  {e['subject']} ({e['exam_type']}): {e['score']}/{e['max_score']} ({pct}%)"
            )

    report_lines.append(f"\n💬 <b>Аналитика:</b>\n{summary}")
    await message.answer("\n".join(report_lines), parse_mode="HTML")

    if subjects_perf and tasks_month > 0:
        await _send_progress_chart(message, student_id, student_name)


async def _send_progress_chart(message: Message, student_id: int, student_name: str) -> None:
    try:
        conn = db.get_connection()
        logs = conn.execute(
            "SELECT subject, correct, timestamp FROM homework_log WHERE student_id = ? ORDER BY timestamp",
            (student_id,),
        ).fetchall()
        conn.close()

        if not logs:
            return

        weekly_stats = aggregate_weekly_stats([dict(l) for l in logs])
        if not weekly_stats:
            return

        chart_bytes = build_progress_chart(weekly_stats, student_name)
        await message.answer_photo(
            BufferedInputFile(chart_bytes, filename="progress.png"),
            caption=f"📈 График успеваемости — {student_name}",
        )
    except Exception as e:
        logger.error(f"Ошибка построения графика: {e}")


async def _send_subject_pie(message: Message, student_id: int, student_name: str) -> None:
    try:
        stats = db.get_homework_stats(student_id, days=30)
        if not stats:
            return
        pie_bytes = build_subject_pie(stats, student_name)
        await message.answer_photo(
            BufferedInputFile(pie_bytes, filename="subjects.png"),
            caption=f"📊 Доля правильных ответов — {student_name}",
        )
    except Exception as e:
        logger.error(f"Ошибка построения диаграммы: {e}")
