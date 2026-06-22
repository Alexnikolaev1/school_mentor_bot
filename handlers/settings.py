"""
Хэндлер настроек профиля ученика и личной статистики.
"""
import json
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import SUBJECTS, GRADES, LEVELS
from keyboards import (
    main_menu_keyboard,
    settings_keyboard,
    study_time_keyboard,
    level_keyboard,
    timezone_keyboard,
    grade_keyboard,
    remove_keyboard,
)
from utils.helpers import progress_bar

logger = logging.getLogger(__name__)
router = Router()


class SettingsStates(StatesGroup):
    main_menu = State()
    changing_name = State()
    changing_grade = State()
    changing_subjects = State()
    changing_time = State()
    changing_level = State()
    changing_timezone = State()


@router.message(F.text == "⚙️ Настройки")
@router.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    student = db.get_student(user_id)
    if not student:
        await message.answer("Сначала зарегистрируйся! /start")
        return

    subjects = json.loads(student.get("subjects", "[]")) or ["не выбраны"]
    level_name = LEVELS.get(student.get("level", "intermediate"), "средний")

    await message.answer(
        f"⚙️ <b>Настройки профиля</b>\n\n"
        f"👤 Имя: {student.get('name', '—')}\n"
        f"🎓 Класс: {student.get('grade', '—')}\n"
        f"📚 Предметы: {', '.join(subjects)}\n"
        f"📊 Уровень: {level_name}\n"
        f"⏰ Время занятий: {student.get('study_time', '17:00')}\n"
        f"🌍 Часовой пояс: {student.get('timezone', 'Europe/Moscow')}\n\n"
        "Что хочешь изменить?",
        parse_mode="HTML",
        reply_markup=settings_keyboard(),
    )
    await state.set_state(SettingsStates.main_menu)


@router.message(SettingsStates.main_menu, F.text == "◀️ Назад")
async def settings_back(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard())


@router.message(SettingsStates.main_menu, F.text == "✏️ Изменить имя")
async def change_name_start(message: Message, state: FSMContext) -> None:
    await message.answer("Введи новое имя:", reply_markup=remove_keyboard())
    await state.set_state(SettingsStates.changing_name)


@router.message(SettingsStates.changing_name)
async def change_name_done(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if 2 <= len(name) <= 50:
        db.upsert_student(message.from_user.id, name=name)
        await message.answer(f"✅ Имя изменено на «{name}»")
    else:
        await message.answer("Имя от 2 до 50 символов. Попробуй ещё раз:")
        return
    await cmd_settings(message, state)


@router.message(SettingsStates.main_menu, F.text == "🎓 Изменить класс")
async def change_grade_start(message: Message, state: FSMContext) -> None:
    await message.answer("Выбери класс:", reply_markup=grade_keyboard())
    await state.set_state(SettingsStates.changing_grade)


@router.message(SettingsStates.changing_grade)
async def change_grade_done(message: Message, state: FSMContext) -> None:
    try:
        grade = int(message.text.strip())
        if grade not in GRADES:
            raise ValueError
        db.upsert_student(message.from_user.id, grade=grade)
        await message.answer(f"✅ Класс изменён на {grade}")
    except ValueError:
        await message.answer("Выбери класс от 5 до 11:")
        return
    await cmd_settings(message, state)


@router.message(SettingsStates.main_menu, F.text == "📚 Предметы")
async def change_subjects_start(message: Message, state: FSMContext) -> None:
    from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
    rows = [[KeyboardButton(text=s) for s in SUBJECTS[i:i + 3]] for i in range(0, len(SUBJECTS), 3)]
    rows.append([KeyboardButton(text="✅ Готово")])
    await message.answer(
        "Выбери предметы (нажимай по одному, потом «Готово»):",
        reply_markup=ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True),
    )
    await state.set_state(SettingsStates.changing_subjects)
    await state.update_data(selected_subjects=[])


@router.message(SettingsStates.changing_subjects)
async def change_subjects(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    data = await state.get_data()
    selected = data.get("selected_subjects", [])

    if text == "✅ Готово":
        if selected:
            db.upsert_student(
                message.from_user.id,
                subjects=json.dumps(selected, ensure_ascii=False),
            )
            await message.answer(f"✅ Предметы сохранены: {', '.join(selected)}")
            await cmd_settings(message, state)
        else:
            await message.answer("Выбери хотя бы один предмет!")
        return

    if text in SUBJECTS:
        if text not in selected:
            selected.append(text)
        else:
            selected.remove(text)
        await state.update_data(selected_subjects=selected)
        await message.answer(
            f"Выбрано: {', '.join(selected) if selected else 'ничего'}\n"
            "Добавляй ещё или нажми ✅ Готово"
        )
    else:
        await message.answer("Выбери предмет из списка или нажми ✅ Готово")


@router.message(SettingsStates.main_menu, F.text == "⏰ Время занятий")
async def change_time_start(message: Message, state: FSMContext) -> None:
    await message.answer(
        "Когда присылать ежедневные задания?\nВыбери или введи в формате ЧЧ:ММ:",
        reply_markup=study_time_keyboard(),
    )
    await state.set_state(SettingsStates.changing_time)


@router.message(SettingsStates.changing_time)
async def change_time_done(message: Message, state: FSMContext) -> None:
    import re
    text = message.text.strip()
    if re.match(r"^\d{1,2}:\d{2}$", text):
        db.upsert_student(message.from_user.id, study_time=text)
        await message.answer(f"✅ Время занятий: {text}")
        await cmd_settings(message, state)
    else:
        await message.answer("Введи время в формате ЧЧ:ММ, например 17:00")


@router.message(SettingsStates.main_menu, F.text == "📊 Уровень")
async def change_level_start(message: Message, state: FSMContext) -> None:
    await message.answer(
        "Выбери свой уровень подготовки:\n\n"
        "🟢 Начальный — только осваиваю предмет\n"
        "🟡 Средний — знаю базу, хочу углубиться\n"
        "🔴 Продвинутый — готовлюсь к олимпиадам/ЕГЭ на 90+",
        reply_markup=level_keyboard(),
    )
    await state.set_state(SettingsStates.changing_level)


@router.message(SettingsStates.changing_level)
async def change_level_done(message: Message, state: FSMContext) -> None:
    text = message.text.lower()
    level_map = {"начальный": "beginner", "средний": "intermediate", "продвинутый": "advanced"}
    for key, val in level_map.items():
        if key in text:
            db.upsert_student(message.from_user.id, level=val)
            await message.answer(f"✅ Уровень: {LEVELS[val]}")
            await cmd_settings(message, state)
            return
    await message.answer("Выбери один из вариантов:")


@router.message(SettingsStates.main_menu, F.text == "🌍 Часовой пояс")
async def change_tz_start(message: Message, state: FSMContext) -> None:
    await message.answer("Выбери часовой пояс:", reply_markup=timezone_keyboard())
    await state.set_state(SettingsStates.changing_timezone)


@router.message(SettingsStates.changing_timezone)
async def change_tz_done(message: Message, state: FSMContext) -> None:
    from config import TIMEZONES
    tz = message.text.strip()
    if tz in TIMEZONES:
        db.upsert_student(message.from_user.id, timezone=tz)
        await message.answer(f"✅ Часовой пояс: {tz}")
        await cmd_settings(message, state)
    else:
        await message.answer("Выбери из списка:")


@router.message(F.text == "📈 Успеваемость")
@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    user_id = message.from_user.id
    student = db.get_student(user_id)
    if not student:
        await message.answer("Сначала зарегистрируйся! /start")
        return

    stats_today = db.get_homework_stats(user_id, days=1)
    stats_week = db.get_homework_stats(user_id, days=7)
    stats_month = db.get_homework_stats(user_id, days=30)

    today_total = sum(s.get("total", 0) for s in stats_today)
    week_total = sum(s.get("total", 0) for s in stats_week)
    month_total = sum(s.get("total", 0) for s in stats_month)

    exams = db.get_exam_results(user_id, limit=5)
    plan = db.get_study_plan(user_id)

    name = student.get("name", "Ученик")
    grade = student.get("grade", "?")
    level_name = LEVELS.get(student.get("level", "intermediate"), "средний")

    lines = [
        f"📈 <b>Статистика — {name}</b> | {grade} класс | {level_name}\n",
        f"📅 <b>Задач решено:</b>",
        f"  Сегодня: {today_total}",
        f"  За неделю: {week_total}",
        f"  За месяц: {month_total}",
    ]

    if stats_week:
        lines.append("\n📚 <b>Успеваемость по предметам (неделя):</b>")
        for s in sorted(stats_week, key=lambda x: -x.get("correct_count", 0)):
            total = s.get("total", 0)
            correct = s.get("correct_count", 0)
            pct = round(correct / total * 100) if total else 0
            lines.append(f"  {s['subject']}: {progress_bar(pct)} {pct}%")

    if exams:
        lines.append("\n🎓 <b>Последние экзамены:</b>")
        for e in exams[:3]:
            pct = round(e["score"] / e["max_score"] * 100) if e["max_score"] else 0
            dt = e["timestamp"][:10] if e.get("timestamp") else "?"
            lines.append(f"  {e['subject']} {e['exam_type']}: {e['score']}/{e['max_score']} ({pct}%) — {dt}")

    if plan:
        lines.append(f"\n📋 <b>Учебный план ({len(plan)} тем):</b>")
        for p in plan[:4]:
            priority_icon = {1: "🔴", 2: "🟡", 3: "🟢"}.get(p.get("priority"), "🔵")
            lines.append(f"  {priority_icon} {p['subject']}: {p['topic']}")
        if len(plan) > 4:
            lines.append(f"  ... и ещё {len(plan) - 4} тем")
        lines.append("\n💡 Изучи тему и напиши /done когда готов")

    if week_total == 0:
        lines.append("\n💡 Начни с /diagnostic чтобы узнать свой уровень!")
    elif week_total < 10:
        lines.append("\n💪 Хорошее начало! Занимайся каждый день для лучших результатов.")
    else:
        lines.append("\n🌟 Отличный темп! Продолжай в том же духе!")

    await message.answer("\n".join(lines), parse_mode="HTML")
