import aiohttp
import google.generativeai as genai
import asyncio
from typing import List, Dict, Any
from .config import settings
from tenacity import retry, wait_exponential, stop_after_attempt
import logging

log = logging.getLogger(__name__)

genai.configure(api_key=settings.gemini_api_key.get_secret_value())

# Стабильная модель на декабрь 2025
main_model = genai.GenerativeModel("gemini-2.0-flash-exp")

search_decision_model = genai.GenerativeModel("gemini-2.0-flash-exp")

GEMINI_SEMAPHORE = asyncio.Semaphore(8)


async def should_use_search(user_message: str) -> bool:
    prompt = f"""Ответь только YES или NO.
Нужно ли искать актуальную информацию в интернете (новости, погода, курсы валют, цены, события после 2024 года) 
для точного ответа на вопрос:

"{user_message}"

Ответ: """
    try:
        async with GEMINI_SEMAPHORE:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: search_decision_model.generate_content(
                    prompt,
                    generation_config={"temperature": 0.0, "max_output_tokens": 5}
                )
            )
            return "YES" in response.text.strip().upper()
    except Exception as e:
        log.warning(f"Ошибка при решении о поиске: {e}")
        return False


async def google_search(query: str, num: int = 3) -> str:
    if not settings.google_api_key or not settings.google_cse_id:
        return ""
    params = {
        "key": settings.google_api_key,
        "cx": settings.google_cse_id,
        "q": query,
        "num": num,
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=7)) as s:
            async with s.get("https://www.googleapis.com/customsearch/v1", params=params) as r:
                if r.status != 200:
                    return "Поиск временно недоступен."
                items = (await r.json()).get("items", [])
                return "\n\n".join(f"{i+1}. {it['title']}\n{it['snippet']}" for i, it in enumerate(items))
    except Exception:
        return "Поиск временно недоступен."


@retry(wait=wait_exponential(multiplier=1, min=4, max=15), stop=stop_after_attempt(4))
async def gemini_reply(history: List[Dict[str, Any]]) -> str:
    async with GEMINI_SEMAPHORE:
        chat_history = history[-40:] if history else []
        chat = main_model.start_chat(history=chat_history)
        
        # Системный промпт добавляем в историю (для совместимости)
        system_prompt = "Ты — полезный и остроумный помощник в Telegram. Отвечай на русском языке, кратко и по делу."
        full_history = [{"role": "model", "parts": [system_prompt]}] + chat_history
        
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, lambda: chat.send_message(""))
        if not response.candidates:
            return "Извини, Google заблокировал ответ по правилам безопасности."
        return response.text