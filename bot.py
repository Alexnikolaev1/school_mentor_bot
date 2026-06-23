"""
SCHOOL.AI Bot — Точка входа
Поддерживает webhook (Railway) и polling (локально).
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

from config import (
    TELEGRAM_BOT_TOKEN, WEBHOOK_URL, WEBHOOK_PATH, PORT,
    GEMINI_API_KEY, WOLFRAM_APP_ID, SCHEDULER_INTERVAL_SEC,
)
import database as db
from utils.cache import cleanup_cache
from middleware import ErrorHandlerMiddleware, StudentContextMiddleware
from services.http_client import close_session

from handlers import start, explain, homework, diagnostic, exam, voice, parent, settings, encyclopedia

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def check_config() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY не задан — большинство функций не будут работать")
    if not WOLFRAM_APP_ID:
        logger.warning("WOLFRAM_APP_ID не задан — решение задач будет только через Gemini")


def create_bot() -> Bot:
    return Bot(
        token=TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(ErrorHandlerMiddleware())
    dp.message.middleware(StudentContextMiddleware())

    dp.include_router(start.router)
    dp.include_router(voice.router)
    dp.include_router(homework.router)
    dp.include_router(diagnostic.router)
    dp.include_router(exam.router)
    dp.include_router(settings.router)
    dp.include_router(parent.router)
    dp.include_router(encyclopedia.router)
    dp.include_router(explain.router)

    return dp


async def on_startup(bot: Bot) -> None:
    db.init_db()
    cleanup_cache()

    if WEBHOOK_URL:
        webhook_full_url = WEBHOOK_URL.rstrip("/") + WEBHOOK_PATH
        await bot.set_webhook(url=webhook_full_url, drop_pending_updates=True)
        logger.info(f"Webhook установлен: {webhook_full_url}")
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Polling режим")

    me = await bot.get_me()
    logger.info(f"Бот запущен: @{me.username} ({me.id})")


async def on_shutdown(bot: Bot) -> None:
    if WEBHOOK_URL:
        await bot.delete_webhook()
    await close_session()
    logger.info("Бот остановлен")


async def run_polling(bot: Bot, dp: Dispatcher) -> None:
    await on_startup(bot)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await on_shutdown(bot)


async def run_webhook(bot: Bot, dp: Dispatcher) -> None:
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    await on_startup(bot)

    app = web.Application()
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    async def health(_request):
        return web.Response(text="OK")

    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
    await site.start()
    logger.info(f"Webhook сервер запущен на порту {PORT}")

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await on_shutdown(bot)


async def daily_lesson_scheduler(bot: Bot) -> None:
    """
    Периодически проверяет, кому пора получить ежедневное задание.
    Учитывает часовой пояс ученика, не дублирует напоминания за день.
    """
    from utils.timezone import is_study_time

    while True:
        try:
            await asyncio.sleep(SCHEDULER_INTERVAL_SEC)

            for student in db.get_students_for_reminder():
                user_id = student["user_id"]
                study_time = student.get("study_time") or "17:00"
                timezone = student.get("timezone") or "Europe/Moscow"

                if not is_study_time(study_time, timezone):
                    continue
                if db.was_reminder_sent_today(user_id):
                    continue

                topic = db.get_next_study_topic(user_id)
                if not topic:
                    continue

                try:
                    db.set_active_topic(user_id, topic["id"])
                    await bot.send_message(
                        user_id,
                        f"📚 <b>Ежедневное занятие</b>\n\n"
                        f"📌 Тема: <b>{topic['topic']}</b>\n"
                        f"Предмет: {topic['subject']}\n\n"
                        f"Напиши вопрос по этой теме или попроси объяснить!\n"
                        f"Когда закончишь — напиши /done",
                        parse_mode="HTML",
                    )
                    db.mark_reminder_sent(user_id)
                except Exception as e:
                    logger.debug(f"Не удалось отправить напоминание {user_id}: {e}")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Ошибка планировщика: {e}")


async def main() -> None:
    check_config()
    bot = create_bot()
    dp = create_dispatcher()

    scheduler_task = asyncio.create_task(daily_lesson_scheduler(bot))

    try:
        if WEBHOOK_URL:
            await run_webhook(bot, dp)
        else:
            await run_polling(bot, dp)
    finally:
        scheduler_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
