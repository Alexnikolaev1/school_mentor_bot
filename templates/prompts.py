"""
Централизованное хранилище промтов для Gemini API.
Все промты на русском, адаптируются под класс и уровень ученика.
"""
from config import LEVELS, WOLFRAM_SUBJECTS


def _subjects_hint(student_subjects: list[str] | None) -> str:
    if not student_subjects:
        return ""
    return f"\nУченик изучает: {', '.join(student_subjects)}. Учитывай это при объяснении."


def explain_topic_prompt(
    topic: str,
    subject: str,
    grade: int,
    level: str,
    student_subjects: list[str] | None = None,
) -> str:
    level_name = LEVELS.get(level, "средний")
    return f"""Ты — опытный учитель {subject} для школьников.
Объясни тему «{topic}» ученику {grade} класса с {level_name} уровнем подготовки.{_subjects_hint(student_subjects)}

Требования к объяснению:
1. Начни с простого определения или аналогии из жизни
2. Дай 2-3 ключевых правила или формулы
3. Разбери 2 примера (простой и чуть сложнее)
4. В конце — краткое резюме (3-4 предложения)
5. Используй эмодзи для структурирования (📌, ✅, 💡, 📝)
6. Длина: 300-500 слов
7. Пиши живым, понятным языком — без академической воды

Тема: {topic}"""


def solve_task_prompt(
    task: str,
    wolfram_steps: str,
    grade: int,
    subject: str,
    student_subjects: list[str] | None = None,
) -> str:
    hint = _subjects_hint(student_subjects)
    if wolfram_steps:
        return f"""Ты — репетитор по {subject} для ученика {grade} класса.{hint}
Wolfram Alpha решил задачу и дал такие шаги:
{wolfram_steps}

Перепиши это решение простым, понятным школьникам языком:
- Объясни каждый шаг своими словами
- Добавь подсказки «почему мы это делаем»
- В конце напиши: «Ответ: [ответ]»
- Используй формат с нумерованными шагами
Задача: {task}"""
    else:
        return f"""Ты — репетитор по {subject} для ученика {grade} класса.{hint}
Реши следующую задачу пошагово, объясняя каждое действие:
- Используй нумерованные шаги
- Объясняй, ПОЧЕМУ делаешь каждое действие
- В конце: «Ответ: [ответ]»
Задача: {task}"""


def check_homework_photo_prompt() -> str:
    return """На этом фото — домашняя работа школьника.
Распознай все задания с их номерами и решениями.
Верни ТОЛЬКО JSON без пояснений:
{
  "tasks": [
    {
      "number": "1",
      "type": "math",
      "condition": "текст условия задачи",
      "student_answer": "ответ ученика или 'не указан'"
    }
  ],
  "image_quality": "good|blurry|partial"
}

Типы заданий: math, algebra, geometry, physics, chemistry, informatics, russian, literature, history, social_studies, biology
Если фото нечёткое — верни {"image_quality": "blurry", "tasks": []}"""


def check_homework_task_prompt(task_condition: str, student_answer: str,
                                subject: str, grade: int, correct_answer: str = None) -> str:
    if correct_answer:
        return f"""Ты — строгий учитель {subject}.
Задание: {task_condition}
Ответ ученика: {student_answer}
Правильный ответ (из Wolfram Alpha): {correct_answer}

Сравни ответы (учитывай эквивалентные формы записи, округления).
Напиши:
1. ПРАВИЛЬНО или ОШИБКА
2. Если ошибка — объясни в чём ошибка (2-3 предложения)
3. Если ошибка — покажи правильное решение кратко

Формат: JSON {{"correct": true/false, "explanation": "текст"}}"""
    else:
        return f"""Ты — учитель {subject} для {grade} класса. Проверь задание:
Задание: {task_condition}
Ответ ученика: {student_answer}

Оцени правильность, проверь грамотность/стиль/факты.
Напиши JSON: {{"correct": true/false, "explanation": "разбор ошибок или похвала"}}"""


def generate_diagnostic_prompt(subject: str, grade: int) -> str:
    return f"""Ты — методист по {subject}, составляешь диагностический тест.
Создай 10 вопросов по предмету «{subject}» для {grade} класса.
Вопросы должны охватывать разные темы программы и иметь нарастающую сложность.

Верни ТОЛЬКО JSON без пояснений:
{{
  "questions": [
    {{
      "number": 1,
      "topic": "Название темы",
      "text": "Текст вопроса",
      "difficulty": 1,
      "correct_answer": "точный правильный ответ (короткий, одно слово/число/фраза)",
      "explanation": "краткое объяснение (1-2 предложения)"
    }}
  ]
}}

Сложность: 1-3 (1=лёгкий, 2=средний, 3=сложный). По 3-4 вопроса каждого уровня."""


def build_study_plan_prompt(subject: str, weak_topics: list[str], grade: int) -> str:
    topics_str = "\n".join(f"- {t}" for t in weak_topics)
    return f"""Ты — репетитор по {subject} для {grade} класса.
По результатам диагностики ученик плохо знает:
{topics_str}

Составь персональный учебный план: список тем для повторения с приоритетами.
Верни JSON:
{{
  "plan": [
    {{
      "topic": "Название темы",
      "priority": 1,
      "reason": "почему важна (1 предложение)",
      "micro_lesson": "мини-объяснение ключевой идеи (2-3 предложения) + 1 пример"
    }}
  ]
}}
Приоритет: 1=срочно, 2=важно, 3=желательно. Максимум 8 тем."""


def generate_exam_prompt(subject: str, exam_type: str, grade: int) -> str:
    class_label = "9" if exam_type == "OGE" else "11"
    return f"""Ты — эксперт по {exam_type} ({exam_type} по {subject}).
Составь полноценный вариант {exam_type} по предмету «{subject}» для {class_label} класса,
строго соответствующий структуре реального {exam_type} 2024-2025 года.

Верни JSON:
{{
  "exam_type": "{exam_type}",
  "subject": "{subject}",
  "total_tasks": число,
  "tasks": [
    {{
      "number": 1,
      "part": "A",
      "type": "choice|short|extended",
      "text": "текст задания",
      "options": ["вариант1","вариант2","вариант3","вариант4"] или null,
      "correct_answer": "правильный ответ",
      "max_score": число,
      "criteria": "критерии оценки для развёрнутого ответа или null"
    }}
  ]
}}
Типы: choice=с выбором, short=краткий ответ, extended=развёрнутый."""


def grade_extended_answer_prompt(task_text: str, student_answer: str,
                                  criteria: str, subject: str, exam_type: str) -> str:
    return f"""Ты — эксперт-проверяющий {exam_type} по предмету {subject}.
Задание: {task_text}
Критерии оценки: {criteria}
Ответ ученика: {student_answer}

Проверь ответ строго по критериям {exam_type}.
Верни JSON:
{{
  "score": число,
  "max_score": число,
  "verdict": "краткая оценка",
  "feedback": "подробный разбор (что хорошо, что не так, как улучшить)"
}}"""


def progress_summary_prompt(student_name: str, stats: dict) -> str:
    return f"""Ты — педагог-аналитик.
Подготовь краткое резюме успеваемости ученика {student_name} для родителей.

Данные:
- Решено задач за неделю: {stats.get('tasks_week', 0)}
- Решено задач за месяц: {stats.get('tasks_month', 0)}
- Успеваемость по предметам: {stats.get('subjects', {})}
- Последние тесты: {stats.get('last_exams', [])}

Напиши 3-4 абзаца:
1. Общая оценка прогресса
2. Сильные стороны
3. Области для улучшения
4. Рекомендации родителям

Тон: профессиональный, поддерживающий, конкретный. Без воды."""
