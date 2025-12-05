from aiogram import Router, types, F
from aiogram.filters import Command
from .services import gemini_reply, should_use_search, google_search
from .history import get_history, save_history, clear_history
import io
import asyncio

router = Router()


@router.message(Command("start"))
async def start(m: types.Message):
    await clear_history(m.from_user.id)
    await m.answer(
        "Привет! Я бот на Gemini 2.0 Flash\n\n"
        "• Помню весь диалог\n"
        "• Сам решаю, когда искать в Google\n"
        "• Понимаю фото и документы\n\n"
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

    if m.photo:
        photo = m.photo[-1]
        if photo.file_size > 6 * 1024 * 1024:
            await m.answer("Фото слишком большое, максимум 6 МБ")
            return
        file = await m.bot.get_file(photo.file_id)
        photo_bytes = await m.bot.download_file(file.file_path)
        parts.append({"mime_type": "image/jpeg", "data": photo_bytes.read()})

    if m.document and m.document.file_size < 5 * 1024 * 1024:
        file = await m.bot.get_file(m.document.file_id)
        doc_bytes = await m.bot.download_file(file.file_path)
        parts.append({
            "mime_type": m.document.mime_type or "application/octet-stream",
            "data": doc_bytes.read()
        })

    if text:
        parts.insert(0, text)

    if not parts:
        parts.append("")

    hist.append({"role": "user", "parts": parts})

    search_text = text or "фото"
    if await should_use_search(search_text):
        search_result = await google_search(search_text, num=4)
        if search_result:
            hist.append({"role": "model", "parts": [f"Свежие данные из поиска:\n{search_result}"]})

    try:
        answer = await gemini_reply(hist)
    except Exception as e:
        await m.answer("Ошибка связи с Gemini. Попробуй позже.")
        hist.pop()
        await save_history(uid)
        return

    hist.append({"role": "model", "parts": [answer]})
    await save_history(uid)

    if not answer.strip():
        answer = "Не смог ответить 🤷‍♂️"

    for i in range(0, len(answer), 4096):
        chunk = answer[i:i+4096]
        await m.answer(chunk, disable_web_page_preview=True)
        if len(answer) > 4096:
            await asyncio.sleep(0.4)