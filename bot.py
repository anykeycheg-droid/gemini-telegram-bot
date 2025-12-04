import os
import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.webhook import aiohttp_server  # Для webhook
from aiogram.types import ContentType
import google.generativeai as genai
import aiohttp.web as web

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PROJECT_ID = os.getenv("PROJECT_ID")

# Gemini настройка
genai.configure(api_key=GEMINI_API_KEY)
genai.configure(transport="rest")
MODEL = f"projects/{PROJECT_ID}/locations/global/publishers/google/models/gemini-2.5-flash-lite"
model = genai.GenerativeModel(MODEL)

# Бот
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(message):
    await message.answer(
        "Привет! Я на Gemini 2.5 Flash-Lite 2025 ⚡\n"
        "Пиши текст, фото/видео/аудио — отвечу!\n"
        "Webhook режим для Render 24/7."
    )

@dp.message()
async def handle(message):
    user_text = message.text or message.caption or "Опиши"
    
    try:
        content = [user_text]
        
        # Фото
        if message.photo:
            photo = message.photo[-1]
            file = await bot.get_file(photo.file_id)
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}") as resp:
                    data = await resp.read()
            content.append({"mime_type": "image/jpeg", "data": data})
            await message.answer("Анализирую фото...")
        
        # Видео/аудио (упрощённо)
        elif message.video or message.voice or message.audio:
            # Аналогично фото, но mime_type: "video/mp4" или "audio/ogg"
            await message.answer("Обрабатываю медиа...")
            content.append({"mime_type": "video/mp4", "data": b""})  # Заглушка, доработай если нужно
        
        else:
            await message.answer("Думаю...")
        
        response = model.generate_content(
            content,
            generation_config={"temperature": 0.7, "max_output_tokens": 8192}
        )
        
        text = response.text
        for i in range(0, len(text), 4096):
            await message.answer(text[i:i+4096])
            
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

async def on_startup(app):
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook"  # Render даёт hostname
    await bot.set_webhook(webhook_url)
    print(f"Webhook установлен: {webhook_url}")

async def on_shutdown(app):
    await bot.delete_webhook()

async def main():
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    aiohttp_server.setup(app, dp, bot)
    
    # Запуск сервера на порту Render
    port = int(os.getenv("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Сервер запущен на порту {port}")
    
    # Держим живым
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())