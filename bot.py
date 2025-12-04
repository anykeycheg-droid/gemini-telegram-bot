import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
import google.generativeai as genai
import requests  # Для API поиска

# === Конфиг ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === Память ===
user_history = {}
MAX_HISTORY = 30

# === Функция поиска в Google ===
def search_google(query, num=3):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_SEARCH_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "q": query,
        "num": num
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        results = response.json().get("items", [])
        snippets = [f"{item['title']}: {item['snippet']}" for item in results]
        return "\n".join(snippets)
    return "Поиск не удался — проверь ключи."

# === Хэндлеры ===
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    user_history[user_id] = []
    await message.answer(
        "Привет! Я теперь с интернет-поиском 🌐\n"
        "Пиши вопросы с '?' или 'поиск' — найду свежую инфу!\n"
        "Фото тоже анализирую. /clear — очистить память"
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
        user_query = message.text or message.caption
        content.append(user_query)

    if message.photo:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        photo_bytes = await bot.download_file(file.file_path)
        content.append({"mime_type": "image/jpeg", "data": photo_bytes.read()})

    # Проверяем, нужен ли поиск
    search_results = ""
    if "?" in user_query or any(word in user_query.lower() for word in ["поиск", "новости", "узнай", "кто выиграл", "что такое"]):
        await message.answer("Ищу в интернете...")
        search_results = search_google(user_query)
        content.append(f"Свежие данные из поиска:\n{search_results}")

    # Добавляем в историю
    user_history[user_id].append({"role": "user", "parts": content})
    if len(user_history[user_id]) > MAX_HISTORY:
        user_history[user_id] = user_history[user_id][-MAX_HISTORY:]

    try:
        # Генерация с историей и поиском
        chat_session = model.start_chat(history=user_history[user_id][:-1])
        response = chat_session.send_message(content[-1] if len(content) == 1 else content)

        text = response.text

        # Добавляем ответ в историю
        user_history[user_id].append({"role": "model", "parts": [text]})

        # Отправляем
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