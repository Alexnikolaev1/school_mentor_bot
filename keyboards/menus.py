"""Клавиатуры бота."""
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

from config import GRADES, SUBJECTS, TIMEZONES

MAIN_MENU_BUTTONS = (
    ("📚 Объяснить тему", "📝 Проверить ДЗ"),
    ("📊 Диагностика", "🎓 Экзамен"),
    ("📈 Успеваемость", "⚙️ Настройки"),
)


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=b) for b in row] for row in MAIN_MENU_BUTTONS],
        resize_keyboard=True,
    )


def grade_keyboard() -> ReplyKeyboardMarkup:
    buttons, row = [], []
    for grade in GRADES:
        row.append(KeyboardButton(text=str(grade)))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def subjects_keyboard(columns: int = 3) -> ReplyKeyboardMarkup:
    rows, row = [], []
    for subject in SUBJECTS:
        row.append(KeyboardButton(text=subject))
        if len(row) == columns:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def exam_subjects_keyboard() -> ReplyKeyboardMarkup:
    exam_subjects = [
        "Математика", "Русский язык", "Физика", "Химия",
        "Биология", "История", "Обществознание", "Информатика",
    ]
    rows, row = [], []
    for subject in exam_subjects:
        row.append(KeyboardButton(text=subject))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def homework_subjects_keyboard() -> ReplyKeyboardMarkup:
    subjects = [
        "Математика", "Алгебра", "Геометрия", "Физика",
        "Химия", "Русский язык", "История", "Биология",
    ]
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=s) for s in subjects[:4]],
            [KeyboardButton(text=s) for s in subjects[4:]],
        ],
        resize_keyboard=True,
    )


def settings_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✏️ Изменить имя"), KeyboardButton(text="🎓 Изменить класс")],
            [KeyboardButton(text="📚 Предметы"), KeyboardButton(text="⏰ Время занятий")],
            [KeyboardButton(text="📊 Уровень"), KeyboardButton(text="🌍 Часовой пояс")],
            [KeyboardButton(text="◀️ Назад")],
        ],
        resize_keyboard=True,
    )


def exam_type_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text="📘 ОГЭ (9 класс)"),
            KeyboardButton(text="📗 ЕГЭ (11 класс)"),
        ]],
        resize_keyboard=True,
    )


def study_time_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t) for t in ("15:00", "16:00", "17:00")],
            [KeyboardButton(text=t) for t in ("18:00", "19:00", "20:00")],
        ],
        resize_keyboard=True,
    )


def level_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text="🟢 Начальный"),
            KeyboardButton(text="🟡 Средний"),
            KeyboardButton(text="🔴 Продвинутый"),
        ]],
        resize_keyboard=True,
    )


def timezone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=tz)] for tz in TIMEZONES],
        resize_keyboard=True,
    )


def compact_keyboard() -> ReplyKeyboardMarkup:
    """Компактная клавиатура во время тестов/экзаменов."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏹ Стоп"), KeyboardButton(text="🏠 Меню")],
        ],
        resize_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
