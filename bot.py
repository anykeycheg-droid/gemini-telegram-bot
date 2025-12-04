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
PROJECT_ID = os.getenv("PROJECT_ID")          # например tidy-etching-480208

# Самое важное — правильная модель и регион
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash-002")   # ← эта строка решает всё

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Бот жив! Теперь на Gemini 1.5 Flash-002 без ошибки 400")

@dp.message()
async def echo(message: types.Message):
    try:
        await message.answer("Думаю…")
        response = model.generate_content(message.text or " ")
        await message.answer(response.text[:4000])
    except Exception as e:
        await message.answer(f"Ошибка: {str(e)}")

async def main():
    print("Бот запущен на Gemini 1.5 Flash-002")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())