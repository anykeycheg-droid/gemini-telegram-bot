import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
import google.generativeai as genai
import requests

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
user_history = {}           # {user_id: [{"role": "user"/"model", "parts": [...]}, ...]}
MAX_HISTORY = 30

# === Поиск в Google ===
def search_google(query: str, num: int = 3) -> str:
    if not GOOGLE_SEARCH_API_KEY or not GOOGLE_CSE_ID:
        return "Поиск отключён — нет ключей."
    url = "https://www.googleapis.com/customsearch/v1"
    params = {"key": GOOGLE_SEARCH_API_KEY, "cx": GOOGLE_CSE_ID, "q": query, "num": num}
    try:
        r = requests.get(url, params=params, timeout=7)
        if r.status_code == 200:
            items = r.json().get("items", [])
            return "\n\n".join([f"{i+1}. {item['title']}\n{item['snippet']}" for i, item in enumerate(items)])
    except:
        pass
    return "Поиск временно недоступен."

# === Хэндлеры ===
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    user_history[user_id] = []
    await message.answer(
        "Привет! Я умный бот на Gemini 2.5 Flash 🧠\n"
        "• Помню весь диалог\n"
        "• Могу искать в интернете (вопросы с «?» и т.д.)\n"
        "• Понимаю фото\n\n"
        "Команды: /clear — очистить память"
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

    user_text = message.text or message.caption or "Опиши это"
    content = [user_text]

    # Фото
    if message.photo:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        photo_bytes = await bot.download_file(file.file_path)
        content.append({"mime_type": "image/jpeg", "data": photo_bytes.read()})

    # Поиск в интернете
    trigger_words = ["?", "поиск", "новости", "узнай", "кто", "что", "когда", "где", "сколько", "погода", "курс", "цена"]
    if any(word in user_text.lower() for word in trigger_words):
        await message.answer("Ищу в интернете...")
        search_results = search_google(user_text)
        content.append(f"Свежая информация из Google:\n{search_results}")

    # Добавляем в историю
    user_history[user_id].append({"role": "user", "parts": content})
    if len(user_history[user_id]) > MAX_HISTORY:
        user_history[user_id] = user_history[user_id][-MAX_HISTORY:]

    try:
        chat_session = model.start_chat(history=user_history[user_id][:-1])
        response = chat_session.send_message(content[-1] if len(content) == 1 else content)

        # Безопасное извлечение текста (фикс краша)
        try:
            text = response.text
        except ValueError:
            if response.candidates and response.candidates[0].content.parts:
                text = response.candidates[0].content.parts[0].text
            else:
                text = "Google заблокировал ответ по политике безопасности."

        # Сохраняем ответ в историю
        user_history[user_id].append({"role": "model", "parts": [text]})

        # Отправляем пользователю
        for i in range(0, len(text), 4096):
            await message.answer(text[i:i+4096])

    except Exception as e:
        await message.answer(f"Ошибка: {str(e)}")
        user_history[user_id] = []  # сбрасываем при критической ошибке

# === Webhook ===
async def on_startup(app):
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook"
    await bot.set_webhook(webhook_url)
    logging.info(f"Webhook установлен: {webhook_url}")

async def on_shutdown(app):
    await bot.delete_webhook()

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
