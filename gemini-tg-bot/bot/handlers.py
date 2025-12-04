from aiogram import Router, types, F
from aiogram.filters import Command
from .services import google_search, gemini_reply, gemini_should_search
from .config import settings
import io

router = Router()
user_history = {}

def get_hist(uid: int):
    return user_history.setdefault(uid, [])

@router.message(Command("start"))
async def start(m: types.Message):
    get_hist(m.from_user.id).clear()
    await m.answer("Привет! Я бот на Gemini 2.0 🧠\n• Помню диалог (20 пар)\n• Ищу в Google при нужде\n• Понимаю фото\n\n/clear — очистить память")

@router.message(Command("clear"))
async def clear(m: types.Message):
    get_hist(m.from_user.id).clear()
    await m.answer("Память очищена 🧹")

@router.message(F.content_type.in_({"text", "photo"}))
async def chat(m: types.Message):
    uid = m.from_user.id
    hist = get_hist(uid)
    await m.bot.send_chat_action(uid, "typing")
    text = m.text or m.caption or ""
    parts = [text]
    if m.photo:
        photo = m.photo[-1]
        file = await m.bot.get_file(photo.file_id)
        photo_bytes: io.BytesIO = await m.bot.download_file(file.file_path)
        parts.append({"mime_type": "image/jpeg", "data": photo_bytes.read()})
    if gemini_should_search(text):
        parts.append(f"Свежая информация из Google:\n{await google_search(text)}")
    hist.append({"role": "user", "parts": parts})
    if len(hist) > settings.max_history * 2:
        hist[:] = hist[-settings.max_history * 2 :]
    answer = await gemini_reply(hist[:-1], parts[-1])
    hist.append({"role": "model", "parts": [answer]})
    for chunk in (answer[i : i + 4096] for i in range(0, len(answer), 4096)):
        await m.answer(chunk)
