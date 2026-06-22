"""Общие утилиты для хэндлеров."""
import re
from typing import Optional

from config import SUBJECTS

# Кнопки главного меню — не обрабатывать как свободный текст
MENU_BUTTONS = frozenset({
    "📚 Объяснить тему", "📝 Проверить ДЗ", "📊 Диагностика", "🎓 Экзамен",
    "📈 Успеваемость", "⚙️ Настройки",
    "✏️ Изменить имя", "🎓 Изменить класс", "📚 Предметы", "⏰ Время занятий",
    "📊 Уровень", "🌍 Часовой пояс", "◀️ Назад", "✅ Готово",
    "🎒 Я ученик", "👨‍👩‍👧 Я родитель",
    "📘 ОГЭ (9 класс)", "📗 ЕГЭ (11 класс)",
    "⏹ Стоп", "🏠 Меню",
})

TASK_KEYWORDS = [
    "реши", "найди", "вычисли", "решить", "посчитай", "упрости",
    "докажи", "разложи", "интеграл", "производная", "уравнение",
    "неравенство", "задача", "пример", "сколько", "чему равно",
]

SUBJECT_KEYWORDS = {
    "математик": "Математика",
    "алгебр": "Алгебра",
    "геометри": "Геометрия",
    "физик": "Физика",
    "хими": "Химия",
    "информатик": "Информатика",
    "русск": "Русский язык",
    "литератур": "Литература",
    "истори": "История",
    "обществ": "Обществознание",
    "биологи": "Биология",
}


def is_menu_button(text: str) -> bool:
    return text.strip() in MENU_BUTTONS


def match_subject(text: str) -> Optional[str]:
    """Находит предмет по тексту (нечёткое совпадение)."""
    text_lower = text.lower()
    for subject in SUBJECTS:
        if subject.lower() in text_lower or text_lower in subject.lower():
            return subject
    return None


def get_subject_from_text(text: str, default: str = "Математика") -> str:
    """Определяет предмет из текста запроса."""
    text_lower = text.lower()
    for key, subject in SUBJECT_KEYWORDS.items():
        if key in text_lower:
            return subject
    return default


def is_math_task(text: str) -> bool:
    """Определяет, является ли запрос математической задачей."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in TASK_KEYWORDS) or bool(
        re.search(r"[0-9+\-*/=()^√∫]", text)
    )


def compare_answers(user: str, correct: str) -> bool:
    """Сравнивает ответ пользователя с правильным (нечёткое сравнение)."""
    user = user.strip().lower().replace(",", ".").replace(" ", "")
    correct = correct.strip().lower().replace(",", ".").replace(" ", "")
    if user == correct:
        return True
    try:
        return abs(float(user) - float(correct)) < 0.01
    except ValueError:
        pass
    return correct in user or user in correct


def progress_bar(pct: float, length: int = 10) -> str:
    """Текстовая полоса прогресса."""
    filled = round(pct / 100 * length)
    return "█" * filled + "░" * (length - filled)


def parse_student_subjects(subjects_json: str) -> list[str]:
    """Парсит JSON-список предметов ученика."""
    import json
    try:
        subjects = json.loads(subjects_json or "[]")
        return subjects if isinstance(subjects, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
