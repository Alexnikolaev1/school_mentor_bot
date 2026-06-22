"""
Хэндлер голосовых сообщений.
Использует Groq Whisper для транскрибации, затем передаёт в explain.py.
"""
import logging

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

import database as db
from services.groq_service import transcribe_audio

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.voice)
async def handle_voice_message(message: Message, state: FSMContext) -> None:
    """Обрабатывает голосовое сообщение."""
    user_id = message.from_user.id

    if not db.get_student(user_id):
        await message.answer("Сначала зарегистрируйся! Напиши /start")
        return

    current_state = await state.get_state()
    if current_state and ("Diagnostic" in current_state or "Exam" in current_state):
        await message.answer("Во время теста отвечай текстом ✍️")
        return

    # Скачиваем аудиофайл
    status = await message.answer("🎤 Слушаю...")

    try:
        voice = message.voice
        bot = message.bot
        file = await bot.get_file(voice.file_id)
        file_bytes = await bot.download_file(file.file_path)
        audio_data = file_bytes.read() if hasattr(file_bytes, "read") else bytes(file_bytes)
    except Exception as e:
        logger.error(f"Voice: ошибка скачивания: {e}")
        await status.edit_text("❌ Не удалось загрузить аудио. Попробуй ещё раз.")
        return

    await status.edit_text("🎙️ Распознаю речь...")

    # Транскрибация через Groq Whisper
    transcript = await transcribe_audio(audio_data, filename="voice.ogg")

    if not transcript:
        await status.edit_text(
            "❌ Не удалось распознать речь.\n"
            "Попробуй говорить чётче или напиши вопрос текстом."
        )
        return

    await status.edit_text(f"📝 Распознал: «{transcript}»\n\nОбрабатываю...")

    # Передаём в хэндлер объяснений
    from handlers.explain import process_text_question
    await process_text_question(message, transcript)
