# handlers.py — ФИНАЛЬНАЯ ВЕРСИЯ, работает на Render + google-genai (декабрь 2025)
from aiogram import Router, types, F
from aiogram.filters import Command
from .services import gemini_reply, should_use_search, google_search
from .history import get_history, save_history, clear_history

# ← ВАЖНО: только из новой библиотеки google-genai
from google.genai.types import Part, Blob

import asyncio

router = Router()


@router.message(Command("start"))
async def start(m: types.Message):
    await clear_history(m.from_user.id)
    await m.answer(
        "Привет! Я бот на Gemini 2.0 Flash\n\n"
        "• Помню весь диалог\n"
        "• Сам решаю, когда гуглить\n"
        "• Понимаю фото и документы\n"
        "• Быстро и по-русски\n\n"
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
    parts = []

    if text:
        parts.append(text)

    if m.photo:
        photo = m.photo[-1]
        if photo.file_size and photo.file_size > 8 * 1024 * 1024:
            await m.answer("Фото слишком большое (>8 МБ)")
            return
        file = await m.bot.get_file(photo.file_id)
        photo_bytes = await m.bot.download_file(file.file_path)
        parts.append(Part(inline_data=Blob(mime_type="image/jpeg", data=photo_bytes.read())))

    if m.document:
        if m.document.file_size and m.document.file_size > 10 * 1024 * 1024:
            await m.answer("Файл слишком большой (>10 МБ)")
            return
        file = await m.bot.get_file(m.document.file_id)
        doc_bytes = await m.bot.download_file(file.file_path)
        mime = m.document.mime_type or "application/octet-stream"
        parts.append(Part(inline_data=Blob(mime_type=mime, data=doc_bytes.read())))

    if not parts:
        parts.append("")

    hist.append({"role": "user", "parts": parts})

    search_query = text or ("фото" if m.photo else "документ")
    if await should_use_search(search_query):
        search_result = await google_search(search_query)
        if search_result:
            hist.append({"role": "model", "parts": [f"Свежие данные:\n{search_result}"]})

    try:
        answer = await gemini_reply(hist)
    except Exception:
        await m.answer("Ошибка связи с Gemini, попробуй позже")
        hist.pop()
        await save_history(uid)
        return

    hist.append({"role": "model", "parts": [answer]})
    await save_history(uid)

    if not answer.strip():
        answer = "Не знаю, что сказать"

    for i in range(0, len(answer), 4090):
        await m.answer(answer[i:i+4090], disable_web_page_preview=True)
        if i + 4090 < len(answer):
            await asyncio.sleep(0.4)