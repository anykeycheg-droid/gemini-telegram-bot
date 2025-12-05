# services.py — финальная, проверенная на фото и документах (декабрь 2025)
import google.generativeai as genai
import asyncio
from typing import List, Dict, Any
from .config import settings
from tenacity import retry, wait_exponential, stop_after_attempt
import logging
import aiohttp

log = logging.getLogger(__name__)

genai.configure(api_key=settings.gemini_api_key.get_secret_value())

# Актуальная модель с system_instruction
model = genai.GenerativeModel(
    "gemini-2.0-flash",
    system_instruction="Ты — умный и остроумный помощник в Telegram. Отвечай кратко, по-русски, с юмором когда уместно."
)

GEMINI_SEMAPHORE = asyncio.Semaphore(10)


async def should_use_search(text: str) -> bool:
    prompt = f"Ответь только YES или NO: нужно ли гуглить для точного ответа?\n\n{text}"
    try:
        async with GEMINI_SEMAPHORE:
            resp = await model.generate_content_async(
                prompt,
                generation_config={"temperature": 0, "max_output_tokens": 3}
            )
            return "YES" in resp.text.strip().upper()
    except Exception as e:
        log.warning(f"Search decision error: {e}")
        return False


async def google_search(query: str, num: int = 4) -> str:
    if not settings.google_search_api_key or not settings.google_cse_id:
        return ""
    params = {
        "key": settings.google_search_api_key,
        "cx": settings.google_cse_id,
        "q": query,
        "num": num
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://www.googleapis.com/customsearch/v1", params=params) as r:
                if r.status != 200:
                    return ""
                data = await r.json()
                items = data.get("items", [])[:num]
                return "\n\n".join(f"{i+1}. {it.get('title','')}\n{it.get('snippet','')}" for i, it in enumerate(items, 1))
    except Exception as e:
        log.warning(f"Google search failed: {e}")
        return ""


@retry(wait=wait_exponential(multiplier=1, min=4, max=12), stop=stop_after_attempt(4))
async def gemini_reply(history: List[Dict[str, Any]]) -> str:
    async with GEMINI_SEMAPHORE:
        # Обрезаем историю до последних 40 сообщений (20 пар)
        chat = model.start_chat(history=history[-40:])
        try:
            response = await chat.send_message_async("")
            return response.text
        except Exception as e:
            log.exception(f"Gemini error: {e}")
            return "Ошибка связи с Gemini, попробуй позже 😔"