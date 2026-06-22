"""
Построение графиков успеваемости для родительского кабинета.
"""
import io
import logging
from datetime import datetime, timedelta

import matplotlib
matplotlib.use("Agg")  # Без дисплея (сервер)
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

logger = logging.getLogger(__name__)

# Цветовая палитра для предметов
SUBJECT_COLORS = [
    "#4285F4", "#EA4335", "#FBBC05", "#34A853",
    "#FF6D00", "#AA00FF", "#00BCD4", "#E91E63",
    "#8BC34A", "#795548", "#607D8B",
]


def build_progress_chart(stats_by_week: dict[str, list[float]], student_name: str) -> bytes:
    """
    Строит line chart успеваемости по предметам.

    stats_by_week: {
        "Математика": [85, 90, 78, 92],  # процент правильных за каждую неделю
        "Физика": [60, 65, 70, 75],
        ...
    }
    Возвращает PNG-байты.
    """
    if not stats_by_week:
        # Возвращаем заглушку
        return _empty_chart("Нет данных для отображения")

    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor("#F8F9FA")
    ax.set_facecolor("#FFFFFF")

    # Количество недель = максимум из всех серий
    max_weeks = max(len(v) for v in stats_by_week.values())
    weeks = [f"Неделя {i+1}" for i in range(max_weeks)]
    x = np.arange(max_weeks)

    for i, (subject, scores) in enumerate(stats_by_week.items()):
        color = SUBJECT_COLORS[i % len(SUBJECT_COLORS)]
        # Дополняем до max_weeks если коротко
        padded = scores + [None] * (max_weeks - len(scores))
        # Фильтруем None для рисования
        valid_x = [j for j, s in enumerate(padded) if s is not None]
        valid_y = [s for s in padded if s is not None]

        ax.plot(valid_x, valid_y, marker="o", linewidth=2.5,
                markersize=6, color=color, label=subject)

        # Подписи значений
        for vx, vy in zip(valid_x, valid_y):
            ax.annotate(f"{vy:.0f}%", (vx, vy),
                        textcoords="offset points", xytext=(0, 8),
                        ha="center", fontsize=8, color=color)

    ax.set_title(f"Успеваемость ученика: {student_name}", fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("Период", fontsize=11)
    ax.set_ylabel("Правильных ответов, %", fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels(weeks, rotation=15, ha="right")
    ax.set_ylim(0, 105)
    ax.yaxis.set_major_formatter(ticker.PercentFormatter())
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def build_subject_pie(stats: list[dict], student_name: str) -> bytes:
    """
    Строит круговую диаграмму доли правильных ответов по предметам.
    stats: [{"subject": "Математика", "total": 10, "correct_count": 8}, ...]
    """
    if not stats:
        return _empty_chart("Нет данных")

    labels = [s["subject"] for s in stats]
    sizes = [s["correct_count"] / max(s["total"], 1) * 100 for s in stats]
    colors = SUBJECT_COLORS[:len(labels)]

    fig, ax = plt.subplots(figsize=(8, 6))
    fig.patch.set_facecolor("#F8F9FA")

    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors,
        autopct="%1.0f%%", startangle=140,
        pctdistance=0.82, wedgeprops={"edgecolor": "white", "linewidth": 2}
    )
    for at in autotexts:
        at.set_fontsize(9)

    ax.set_title(f"Доля правильных ответов\n{student_name}", fontsize=13, fontweight="bold")

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _empty_chart(message: str) -> bytes:
    """Возвращает PNG с текстом-заглушкой."""
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.text(0.5, 0.5, message, ha="center", va="center",
            fontsize=14, color="#666666", transform=ax.transAxes)
    ax.axis("off")
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def aggregate_weekly_stats(homework_logs: list[dict]) -> dict[str, list[float]]:
    """
    Преобразует сырые записи лога ДЗ в формат по неделям для графика.
    Возвращает dict: subject -> [процент_неделя_1, процент_неделя_2, ...]
    """
    from collections import defaultdict
    from datetime import datetime

    # Группируем по (subject, week_number)
    weekly: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))

    now = datetime.utcnow()
    for log in homework_logs:
        ts_str = log.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str[:19])
        except Exception:
            ts = now

        weeks_ago = (now - ts).days // 7
        week_num = -weeks_ago  # 0 = текущая, -1 = прошлая и т.д.
        weekly[log["subject"]][week_num].append(log["correct"])

    # Преобразуем в хронологический список (последние 4 недели)
    result: dict[str, list[float]] = {}
    for subject, weeks_dict in weekly.items():
        min_w = min(weeks_dict.keys())
        max_w = max(weeks_dict.keys())
        series = []
        for w in range(min_w, max_w + 1):
            vals = weeks_dict.get(w, [])
            if vals:
                pct = sum(vals) / len(vals) * 100
            else:
                pct = 0.0
            series.append(round(pct, 1))
        result[subject] = series

    return result
