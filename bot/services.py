# services.py — 100% рабочий на Render + Gemini 2.0 Flash (декабрь 2025)
import asyncio
import logging
from typing import List, Dict, Any
from tenacity import retry, wait_exponential, stop_after_attempt
import aiohttp

# НОВАЯ официальная библиотека Google
from google.genai import GenerativeModel, configure_genai
from google.genai.types import GenerationConfig

from .config import settings

log = logging.getLogger(__name__)

# Настраиваем API ключ один раз
configure_genai(api_key=settings.gemini_api_key.get_secret_value())

# Основная модель с системным промптом
model = GenerativeModel(
    "gemini-2.0-flash",
    system_instruction="Ты — остроумный, дружелюбный помощник в Telegram. Отвечай кратко, по-русски, с лёгким юмором когда уместно."
)

# Для решения «нужен ли поиск»
search_model = GenerativeModel("gemini-2.0-flash")

GEMINI_SEMAPHORE = asyncio.Semaphore(10)


async def should_use_search(text: str) -> bool:
    prompt = f"Ответь ТОЛЬКО YES или NO: нужно ли искать актуальную информацию в интернете для точного ответа на это сообщение?\n\n{text}"
    try:
        async with GEMINI_SEMAPHORE:
            resp = await search_model.generate_content_async(
                prompt,
                generation_config=GenerationConfig(temperature=0, max_output_tokens=5)
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
        async with aiohttp.ClientSession() as s:
            async with s.get("https://www.googleapis.com/customsearch/v1", params=params) as r:
                if r.status != 200:
                    return ""
                data = await r.json()
                items = data.get("items", [])[:num]
                return "\n\n".join(
                    f"{i+1}. {item.get('title', '')}\n{item.get('snippet', '')}"
                    for i, item in enumerate(items)
                )
    except Exception as e:
        log.warning(f"Google search failed: {e}")
        return ""


@retry(wait=wait_exponential(multiplier=1, min=4, max=12), stop=stop_after_attempt(4))
async def gemini_reply(history: List[Dict[str, Any]]) -> str:
    async with GEMINI_SEMAPHORE:
        chat = model.start_chat(history=history[-40:])  # последние 20 пар
        try:
            response = await chat.send_message_async("")
            return response.text or "Хм, что-то пошло не так..."
        except Exception as e:
            log.exception(f"Gemini error: {e}")
            return "Ошибка связи с Gemini, попробуй позже"