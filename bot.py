import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import google.generativeai as genai

# === Переменные окружения ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# === Настройка Gemini (актуальная стабильная модель 2025) ===
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")  # ← Стабильная, бесплатная, мультимодальная

# === Бот ===
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer(
        "Привет! Я бот на Gemini 2.5 Flash (декабрь 2025)\n"
        "Пиши текст, присылай фото — отвечу!\n"
        "Лимит Free: 15 запросов/мин"
    )

@dp.message()
async def handle_message(message: types.Message):
    user_input = message.text or message.caption or "Опиши это"
    try:
        content = [user_input]

        # Поддержка фото
        if message.photo:
            photo = message.photo[-1]
            file = await bot.get_file(photo.file_id)
            photo_bytes = await bot.download_file(file.file_path)
            content.append({
                "mime_type": "image/jpeg",
                "data": photo_bytes.read()
            })
            await message.answer("Анализирую фото...")

        await message.answer("Думаю...")

        response = model.generate_content(
            content,
            generation_config={
                "temperature": 0.7,
                "max_output_tokens": 8192
            }
        )

        text = response.text
        # Разбиваем длинные ответы
        for i in range(0, len(text), 4096):
            await message.answer(text[i:i+4096], disable_web_page_preview=True)

    except Exception as e:
        await message.answer(f"Ошибка: {str(e)}")

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

    # Webhook путь
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)

    # Health check для Render
    async def health(request):
        return web.Response(text="Bot is alive!")
    app.router.add_get("/", health)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    port = int(os.getenv("PORT", 10000))
    logging.basicConfig(level=logging.INFO)
    web.run_app(app, host="0.0.0.0", port=port)