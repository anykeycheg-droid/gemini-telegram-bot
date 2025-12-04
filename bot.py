import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler  # Только это — без aiohttp_server
import google.generativeai as genai

# === Конфиг ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")  # Актуальная бесплатная модель 2025

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === Хэндлеры ===
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Бот жив! Gemini 2.5 Flash работает на Render Free 24/7")

@dp.message()
async def echo(message: types.Message):
    try:
        await message.answer("Думаю...")
        user_text = message.text or message.caption or "Опиши это"

        content = [user_text]
        if message.photo:
            photo = message.photo[-1]
            file = await bot.get_file(photo.file_id)
            photo_bytes = await bot.download_file(file.file_path)
            content.append({"mime_type": "image/jpeg", "data": photo_bytes.read()})

        response = model.generate_content(content)
        text = response.text

        for i in range(0, len(text), 4096):
            await message.answer(text[i:i+4096])

    except Exception as e:
        await message.answer(f"Ошибка: {e}")

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

    # Правильная регистрация webhook (по docs.aiogram.dev v3.13)
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path="/webhook")

    # Health-check для Render (открывает порт)
    async def health(request):
        return web.Response(text="Bot alive!")
    app.router.add_get("/", health)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    port = int(os.getenv("PORT", 10000))
    logging.basicConfig(level=logging.INFO)
    web.run_app(app, host="0.0.0.0", port=port)