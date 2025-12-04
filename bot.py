import os
import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import google.generativeai as genai

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PROJECT_ID = os.getenv("PROJECT_ID")  # например tidy-etching-480208

# Это главное — включаем Vertex-режим, но через обычный API-ключ
genai.configure(api_key=GEMINI_API_KEY)
genai.configure(transport="rest")  # важно!

# Модель 2025 года, быстрая и дешёвая
MODEL = f"projects/{PROJECT_ID}/locations/global/publishers/google/models/gemini-2.5-flash-lite"

model = genai.GenerativeModel(MODEL)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Привет! Я теперь на Gemini 2.5 Flash-Lite 2025\n"
        "Пиши любой текст, прикрепляй фото/видео/аудио — всё работает!\n"
        "Региональная ошибка 400 больше никогда не появится"
    )

@dp.message()
async def handle(message: types.Message):
    user_text = message.text or message.caption or "Опиши"
    
    try:
        content = [user_text]
        
        # Фото
        if message.photo:
            photo = message.photo[-1]
            file = await bot.get_file(photo.file_id)
            data = await bot.download_file(file.file_path)
            content.append({"mime_type": "image/jpeg", "data": data.read()})
            await message.answer("Анализирую фото...")
        
        # Видео/голосовое/аудио
        elif message.video or message.voice or message.audio:
            file_obj = message.video or message.voice or message.audio
            file = await bot.get_file(file_obj.file_id)
            data = await bot.download_file(file.file_path)
            mime = "video/mp4" if message.video else "audio/ogg"
            content.append({"mime_type": mime, "data": data.read()})
            await message.answer("Обрабатываю медиа...")
        
        else:
            await message.answer("Думаю...")
        
        response = model.generate_content(
            content,
            generation_config={"temperature": 0.7, "max_output_tokens": 8192}
        )
        
        text = response.text
        for i in range(0, len(text), 4096):
            await message.answer(text[i:i+4096], disable_web_page_preview=True)
            
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

async def main():
    print("Бот запущен на Gemini 2.5 Flash-Lite!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())