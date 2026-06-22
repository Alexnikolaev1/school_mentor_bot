# SCHOOL.AI Bot — Персональный AI-репетитор

Telegram-бот, заменяющий репетиторов по всем школьным предметам.

## Возможности
- 📚 Объяснение тем по любому предмету (Gemini 1.5 Flash)
- 🧮 Решение задач пошагово (Wolfram Alpha + Gemini)
- 📝 Проверка домашних заданий по фото (Gemini Vision)
- 📊 Диагностика пробелов + персональный учебный план
- 🎓 Пробные ОГЭ/ЕГЭ с проверкой по критериям
- 🎤 Голосовой ввод (Groq Whisper Large v3)
- 🔊 Озвучка ответов (Microsoft Edge TTS)
- 👨‍👩‍👧 Родительский кабинет с графиком успеваемости

## Стек
- Python 3.11+, aiogram 3.x, SQLite, aiohttp
- Gemini 1.5 Flash (бесплатно: 15 RPM / 1M токенов/день)
- Wolfram Alpha (бесплатно: 2000 запросов/месяц)
- Groq Whisper Large v3 (бесплатно)
- Edge TTS (бесплатно, без лимитов)

## Деплой на Railway

### 1. Получи API ключи
- **Telegram Bot Token**: @BotFather → /newbot
- **Gemini API Key**: https://aistudio.google.com/app/apikey
- **Groq API Key**: https://console.groq.com
- **Wolfram App ID**: https://developer.wolframalpha.com

### 2. Деплой на Railway
```bash
# Установи Railway CLI
npm install -g @railway/cli

# Авторизуйся
railway login

# Создай проект
railway init

# Деплой
railway up
```

### 3. Переменные окружения на Railway
В панели Railway → Variables добавь:
```
TELEGRAM_BOT_TOKEN=your_token_here
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
WOLFRAM_APP_ID=your_wolfram_id
WEBHOOK_URL=https://your-app.up.railway.app
```

Railway автоматически установит PORT.

### 4. Локальный запуск (polling)
```bash
pip install -r requirements.txt

export TELEGRAM_BOT_TOKEN=...
export GEMINI_API_KEY=...
export GROQ_API_KEY=...
export WOLFRAM_APP_ID=...

python bot.py
```

## Структура проекта
```
school_bot/
├── bot.py                 # Точка входа
├── config.py              # Конфигурация
├── database.py            # SQLite схема и CRUD
├── requirements.txt
├── Procfile
├── handlers/
│   ├── start.py           # /start, регистрация
│   ├── explain.py         # Объяснение тем и задач
│   ├── homework.py        # Проверка ДЗ по фото
│   ├── diagnostic.py      # Диагностика пробелов
│   ├── exam.py            # ОГЭ/ЕГЭ тренировка
│   ├── voice.py           # Голосовые сообщения
│   ├── parent.py          # Родительский кабинет
│   └── settings.py        # Настройки и статистика
├── services/
│   ├── gemini_service.py  # Gemini API
│   ├── wolfram_service.py # Wolfram Alpha API
│   ├── groq_service.py    # Groq Whisper
│   └── tts.py             # Edge TTS
├── utils/
│   ├── rate_limiter.py    # Rate limiting
│   ├── graph.py           # Matplotlib графики
│   └── cache.py           # Кэширование с TTL
└── templates/
    └── prompts.py         # Промты для Gemini
```

## Rate Limits (бесплатные тиры)
| Сервис | Лимит | Защита в коде |
|--------|-------|---------------|
| Gemini 1.5 Flash | 15 RPM / 1M токенов/день | 5 RPM/пользователь, 14 RPM глобально |
| Wolfram Alpha | 2000 запросов/месяц | 5 RPM |
| Groq Whisper | Без ограничений | — |
| Edge TTS | Без ограничений | — |

## База данных (SQLite)
Файл `school.db` создаётся автоматически при первом запуске.
На Railway БД сбрасывается при редеплое — для persistence используй
Railway Volume или переедь на PostgreSQL (замени sqlite3 на asyncpg).
