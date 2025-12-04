import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import google.generativeai as genai

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash-exp")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("Бот на Gemini 1.5 Flash-002 через webhook на Render Free! Пиши вопрос.")

@dp.message()
async def handle_message(message: types.Message):
    text = message.text or message.caption or "Расскажи о себе"
    try:
        await message.answer("🤔 Думаю...")
        response = model.generate_content(text)
        for chunk in [response.text[i:i+4096] for i in range(0, len(response.text), 4096)]:
            await message.answer(chunk)
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

async def on_startup(app):
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook"
    await bot.set_webhook(webhook_url)
    logging.info(f"Webhook set to {webhook_url}")

async def on_shutdown(app):
    await bot.delete_webhook()

if __name__ == "__main__":
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)
    app.router.add_get("/", lambda _: web.Response(text="Bot is alive!"))  # Для health check Render
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    port = int(os.getenv("PORT", 10000))
    logging.basicConfig(level=logging.INFO)

    web.run_app(app, host="0.0.0.0", port=port)
