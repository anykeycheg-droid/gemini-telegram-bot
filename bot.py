import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
import google.generativeai as genai

# === Конфиг ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === Память диалога (хранится в оперативке, перезапуск Render — сбрасывается) ===
user_history = {}  # {user_id: [{"role": "user"/"model", "parts": [...]}, ...]}

MAX_HISTORY = 30  # сколько сообщений хранить (хватит на длинный диалог)

# === Хэндлеры ===
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    user_history[user_id] = []  # очищаем историю при /start
    await message.answer(
        "Привет! Я теперь помню весь наш диалог 🧠\n"
        "Пиши что угодно, присылай фото — я буду помнить контекст!\n\n"
        "Напиши /clear чтобы очистить память"
    )

@dp.message(Command("clear"))
async def clear(message: types.Message):
    user_id = message.from_user.id
    user_history[user_id] = []
    await message.answer("Память очищена 🧹")

@dp.message()
async def chat(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_history:
        user_history[user_id] = []

    await message.answer("Думаю...")

    # Формируем контент
    content = []
    if message.text or message.caption:
        content.append(message.text or message.caption or "Опиши это")

    if message.photo:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        photo_bytes = await bot.download_file(file.file_path)
        content.append({
            "mime_type": "image/jpeg",
            "data": photo_bytes.read()
        })

    # Добавляем сообщение пользователя в историю
    user_history[user_id].append({"role": "user", "parts": content})

    # Обрезаем историю до MAX_HISTORY
    if len(user_history[user_id]) > MAX_HISTORY:
        user_history[user_id] = user_history[user_id][-MAX_HISTORY:]

    try:
        # Отправляем всю историю
        chat_session = model.start_chat(history=user_history[user_id][:-1])  # кроме последнего (он уже в content)
        response = chat_session.send_message(content[-1] if len(content) == 1 else content)

        text = response.text

        # Добавляем ответ модели в историю
        user_history[user_id].append({"role": "model", "parts": [text]})

        # Отправляем ответ (разбиваем если длинный)
        for i in range(0, len(text), 4096):
            await message.answer(text[i:i+4096])

    except Exception as e:
        await message.answer(f"Ошибка: {e}")
        # При ошибке можно сбросить историю
        user_history[user_id] = []

# === Webhook ===
async def on_startup(app):
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook"
    await bot.set_webhook(webhook_url)
    logging.info(f"Webhook установлен: {webhook_url}")

async def on_shutdown(app):
    await bot.delete_webhook()

# === Запуск ===
if __name__ == "__main__":
    app = web.Application()

    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path="/webhook")

    async def health(request):
        return web.Response(text="Bot alive!")
    app.router.add_get("/", health)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    port = int(os.getenv("PORT", 10000))
    logging.basicConfig(level=logging.INFO)
    web.run_app(app, host="0.0.0.0", port=port)