import google.generativeai as genai
import asyncio
from typing import List, Dict, Any
from .config import settings
from tenacity import retry, wait_exponential, stop_after_attempt
import logging

log = logging.getLogger(__name__)

genai.configure(api_key=settings.gemini_api_key.get_secret_value())

# Актуальная модель на декабрь 2025
main_model = genai.GenerativeModel(
    "gemini-2.0-flash",
    system_instruction="Ты — полезный, остроумный и лаконичный помощник в Telegram. Всегда отвечай на русском языке."
)

search_model = genai.GenerativeModel("gemini-2.0-flash")

GEMINI_SEMAPHORE = asyncio.Semaphore(10)


async def should_use_search(text: str) -> bool:
    prompt = f"Ответь ТОЛЬКО YES или NO: Нужно ли гуглить для ответа на это?\n\n{text}"
    try:
        async with GEMINI_SEMAPHORE:
            response = await search_model.generate_content_async(
                prompt,
                generation_config={"temperature": 0, "max_output_tokens": 3}
            )
            return "YES" in response.text.strip().upper()
    except Exception as e:
        log.warning(f"Search decision failed: {e}")
        return False


async def google_search(query: str, num: int = 4) -> str:
    if not settings.google_search_api_key or not settings.google_cse_id:
        return ""

    import aiohttp
    params = {"key": settings.google_search_api_key, "cx": settings.google_cse_id, "q": query, "num": num}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.get("https://www.googleapis.com/customsearch/v1", params=params) as r:
                if r.status != 200:
                    return ""
                data = await r.json()
                items = data.get("items", [])[:num]
                return "\n\n".join(f"{i+1}. {it.get('title', '')}\n{it.get('snippet', '')}" for i, it in enumerate(items))
    except Exception as e:
        log.warning(f"Google search error: {e}")
        return ""


@retry(wait=wait_exponential(multiplier=1, min=4, max=15), stop=stop_after_attempt(4))
async def gemini_reply(history: List[Dict[str, Any]]) -> str:
    async with GEMINI_SEMAPHORE:
        chat = main_model.start_chat(history=history[-40:])  # 20 пар
        response = await chat.send_message_async("")  # пустое сообщение — модель сама продолжит
        return response.text if response.candidates else "Извини, ответ заблокирован."