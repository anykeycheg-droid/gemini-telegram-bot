import google.generativeai as genai
import asyncio
from typing import List, Dict, Any
from .config import settings
from tenacity import retry, wait_exponential, stop_after_attempt
import logging

log = logging.getLogger(__name__)

# Настраиваем Gemini
genai.configure(api_key=settings.gemini_api_key.get_secret_value())

# Основная модель для ответов
main_model = genai.GenerativeModel(
    "gemini-1.5-flash",
    system_instruction="Ты — полезный и остроумный помощник в Telegram. Отвечай на русском языке, кратко и по делу."
)

# Лёгкая модель только для решения: нужен ли поиск?
search_decision_model = genai.GenerativeModel("gemini-1.5-flash")

# Семфор для ограничения одновременных запросов к Gemini (чтобы не словить 429)
GEMINI_SEMAPHORE = asyncio.Semaphore(8)


async def should_use_search(user_message: str) -> bool:
    """Спрашиваем у самой модели — нужен ли поиск в интернете"""
    prompt = f"""Ответь только YES или NO.
Нужно ли искать актуальную информацию в интернете (новости, погода, курсы валют, цены, события после 2024 года) 
для точного ответа на вопрос:

"{user_message}"

Ответ: """
    try:
        async with GEMINI_SEMAPHORE:
            response = await search_decision_model.generate_content_async(
                prompt,
                generation_config={"temperature": 0.0, "max_output_tokens": 5}
            )
            return "YES" in response.text.strip().upper()
    except Exception as e:
        log.warning(f"Ошибка при решении о поиске: {e}")
        return False


@retry(wait=wait_exponential(multiplier=1, min=4, max=15), stop=stop_after_attempt(4))
async def gemini_reply(history: List[Dict[str, Any]]) -> str:
    """Генерируем ответ с историей (история уже содержит последнее сообщение пользователя)"""
    async with GEMINI_SEMAPHORE:
        chat = main_model.start_chat(history=history[-40:])  # 20 пар ≈ 40 сообщений
        response = await chat.send_message_async("")
        if not response.candidates:
            return "Извини, Google заблокировал ответ по правилам безопасности."
        return response.text