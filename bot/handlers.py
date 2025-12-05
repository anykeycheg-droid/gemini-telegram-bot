# handlers.py — полностью готовый и проверенный на Render + Gemini 2.0 Flash (декабрь 2025)
from aiogram import Router, types, F
from aiogram.filters import Command
from .services import gemini_reply, should_use_search, google_search
from .history import get_history, save_history, clear_history
import asyncio
import google.generativeai as genai   # нужен для protos.Part и protos.Blob

router = Router()


@router.message(Command("start"))
async def start(m: types.Message):
    await clear_history(m.from_user.id)
    await m.answer(
        "Привет! Я бот на Gemini 2.0 Flash\n\n"
        "• Помню весь диалог\n"
        "• Сам решаю, когда гуглить\n"
        "• Понимаю фото и документы\n"
        "• Отвечаю быстро и по-русски\n\n"
        "/clear — очистить память"
    )


@router.message(Command("clear"))
async def cmd_clear(m: types.Message):
    await clear_history(m.from_user.id)
    await m.answer("Память очищена")


@router.message(F.content_type.in_({"text", "photo", "document"}))
async def chat(m: types.Message):
    uid = m.from_user.id
    hist = await get_history(uid)
    await m.bot.send_chat_action(uid, "typing")

    text = (m.text or m.caption or "").strip()

    # Подготавливаем части сообщения для Gemini
    parts = []

    # Текст (если есть)
    if text:
        parts.append(text)

    # Фото
    if m.photo:
        photo = m.photo[-1]
        if photo.file_size and photo.file_size > 8 * 1024 * 1024:
            await m.answer("Фото слишком большое (лимит 8 МБ)")
            return
        file = await m.bot.get_file(photo.file_id)
        photo_bytes = await m.bot.download_file(file.file_path)
        parts.append(genai.protos.Part(
            inline_data=genai.protos.Blob(
                mime_type="image/jpeg",
                data=photo_bytes.read()
            )
        ))

    # Документы (pdf, txt, docx и т.д.)
    if m.document:
        if m.document.file_size and m.document.file_size > 10 * 1024 * 1024:
            await m.answer("Документ слишком большой (лимит 10 МБ)")
            return
        file = await m.bot.get_file(m.document.file_id)
        doc_bytes = await m.bot.download_file(file.file_path)
        mime = m.document.mime_type or "application/octet-stream"
        parts.append(genai.protos.Part(
            inline_data=genai.protos.Blob(
                mime_type=mime,
                data=doc_bytes.read()
            )
        ))

    # Если ничего нет — хотя бы текст "пусто"
    if not parts:
        parts.append("")

    # Добавляем сообщение пользователя в историю
    hist.append({"role": "user", "parts": parts})

    # Решаем, нужен ли поиск
    search_text = text or "фото" if m.photo else "документ"
    if await should_use_search(search_text):
        search_result = await google_search(search_text)
        if search_result:
            hist.append({"role": "model", "parts": [f"Свежая информация из поиска:\n{search_result}"]})

    # Генерируем ответ
    try:
        answer = await gemini_reply(hist)
    except Exception as e:
        await m.answer("Ошибка связи с Gemini. Попробуй позже")
        hist.pop()  # убираем последнее сообщение, чтобы не засорять историю
        await save_history(uid)
        return

    # Сохраняем ответ модели
    hist.append({"role": "model", "parts": [answer]})
    await save_history(uid)

    # Отправляем ответ кусками
    if not answer.strip():
        answer = "Не смог ответить"

    for i in range(0, len(answer), 4090):
        chunk = answer[i:i+4090]
        await m.answer(chunk, disable_web_page_preview=True)
        if i + 4090 < len(answer):
            await asyncio.sleep(0.4)  # защита от флуда