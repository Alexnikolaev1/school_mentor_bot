"""
Хэндлер /start, онбординг нового пользователя.
"""
import logging

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import LEVELS
from keyboards import main_menu_keyboard, grade_keyboard, remove_keyboard

logger = logging.getLogger(__name__)
router = Router()


class RegistrationStates(StatesGroup):
    waiting_name = State()
    waiting_grade = State()
    waiting_role = State()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    student = db.get_student(user_id)
    parent = db.get_parent(user_id)

    if student:
        name = student.get("name") or message.from_user.first_name
        await message.answer(
            f"👋 С возвращением, {name}!\n"
            f"Класс: {student['grade']}, уровень: {LEVELS.get(student['level'], 'средний')}\n\n"
            "Выбери, что будем делать:",
            reply_markup=main_menu_keyboard(),
        )
        return

    if parent:
        await message.answer(
            f"👋 Привет, {parent['name']}!\nТы зарегистрирован как родитель.\n"
            "Используй /progress для отчёта об успеваемости.",
            reply_markup=remove_keyboard(),
        )
        return

    await message.answer(
        "👋 Добро пожаловать в <b>SCHOOL.AI</b>!\n\n"
        "Я — персональный AI-репетитор по всем школьным предметам 🎓\n\n"
        "Давай познакомимся. Как тебя зовут?",
        parse_mode="HTML",
        reply_markup=remove_keyboard(),
    )
    await state.set_state(RegistrationStates.waiting_name)


@router.message(RegistrationStates.waiting_name)
async def reg_got_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 2 or len(name) > 50:
        await message.answer("Имя должно быть от 2 до 50 символов. Попробуй ещё раз:")
        return

    await state.update_data(name=name)
    await message.answer(
        f"Отлично, {name}! 👍\n\nТы ученик или родитель?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[
                KeyboardButton(text="🎒 Я ученик"),
                KeyboardButton(text="👨‍👩‍👧 Я родитель"),
            ]],
            resize_keyboard=True,
        ),
    )
    await state.set_state(RegistrationStates.waiting_role)


@router.message(RegistrationStates.waiting_role)
async def reg_got_role(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    data = await state.get_data()

    if "ученик" in text.lower():
        await state.update_data(role="student")
        await message.answer("В каком ты классе? Выбери:", reply_markup=grade_keyboard())
        await state.set_state(RegistrationStates.waiting_grade)

    elif "родитель" in text.lower():
        db.upsert_parent(message.from_user.id, data["name"])
        await state.clear()
        await message.answer(
            f"✅ Зарегистрирован как родитель!\n\n"
            "Чтобы подключиться к аккаунту ребёнка:\n"
            "1. Ребёнок пишет /invite\n"
            "2. Ты пишешь: /parent КОД\n\n"
            "Команды: /progress, /progress_chart",
            reply_markup=remove_keyboard(),
        )
    else:
        await message.answer("Нажми одну из кнопок: 🎒 Я ученик или 👨‍👩‍👧 Я родитель")


@router.message(RegistrationStates.waiting_grade)
async def reg_got_grade(message: Message, state: FSMContext) -> None:
    from config import GRADES
    try:
        grade = int(message.text.strip())
        if grade not in GRADES:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("Выбери класс от 5 до 11:")
        return

    data = await state.get_data()
    db.upsert_student(
        message.from_user.id,
        name=data["name"],
        grade=grade,
        subjects="[]",
        level="intermediate",
    )
    await state.clear()

    await message.answer(
        f"🎉 <b>Регистрация завершена!</b>\n\n"
        f"Имя: {data['name']}\n"
        f"Класс: {grade}\n\n"
        "Можешь писать вопросы прямо в чат или использовать меню 👇",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "📖 <b>Команды SCHOOL.AI:</b>\n\n"
        "📚 <b>Объяснить тему</b> — объяснение любой темы\n"
        "📝 <b>Проверить ДЗ</b> — отправь фото тетради\n"
        "📊 /diagnostic [предмет] — диагностика пробелов\n"
        "🎓 /exam [предмет] — пробный ОГЭ/ЕГЭ\n"
        "📈 /stats — личная статистика\n"
        "✅ /done — отметить тему учебного плана\n"
        "⚙️ /settings — настройки профиля\n"
        "🔗 /invite — код приглашения для родителей\n\n"
        "Голосовые сообщения тоже работают! 🎤",
        parse_mode="HTML",
    )
