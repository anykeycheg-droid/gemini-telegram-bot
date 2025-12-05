import asyncio
import logging
import aiohttp
from typing import List, Dict, Any
from tenacity import retry, wait_exponential, stop_after_attempt

from google import genai
from google.genai.types import GenerationConfig, Part, Blob

from .config import settings

log = logging.getLogger(__name__)

# Клиент для новой SDK
client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())

MAIN_MODEL = "gemini-2.0-flash"
SEARCH_MODEL = "gemini-2.0-flash"

SEM = asyncio.Semaphore(10)


async def should_use_search(text: str) -> bool:
    prompt = f"Ответь только YES или NO: нужно ли гуглить для ответа?\n\n{text}"
    try:
        async with SEM:
            response = await client.models.generate_content_async(
                model=SEARCH_MODEL,
                contents=prompt,
                generation_config=GenerationConfig(temperature=0.0, max_output_tokens=5)
            )
            return "YES" in response.text.strip().upper()
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
    async with SEM:
        # Системный промпт в начало истории
        system_prompt = "Ты — полезный и остроумный помощник в Telegram. Отвечай на русском языке, кратко и по делу."
        full_history = [{"role": "model", "parts": [system_prompt]}]
        for msg in history[-40:]:
            full_history.append({"role": msg["role"], "parts": msg["parts"]})
        
        try:
            response = await client.models.generate_content_async(
                model=MAIN_MODEL,
                contents=full_history,
                generation_config=GenerationConfig(temperature=0.7)
            )
            if not response.candidates:
                return "Извини, Google заблокировал ответ по правилам безопасности."
            return response.text
        except Exception as e:
            log.exception(f"Gemini error: {e}")
            return "Ошибка связи с Gemini, попробуй позже"