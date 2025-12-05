import aiohttp
import google.generativeai as genai
import asyncio
from typing import List
from .config import settings
from tenacity import retry, wait_fixed, stop_after_attempt

genai.configure(api_key=settings.gemini_api_key.get_secret_value())
gemini_model = genai.GenerativeModel("gemini-2.0-flash-lite")

async def google_search(query: str, num: int = 3) -> str:
    if not settings.google_api_key or not settings.google_cse_id:
        return ""   # ничего не добавляем, если нет ключей
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

def gemini_should_search(text: str) -> bool:
    t = text.lower()
    return (len(text) > 15 and "?" in t) or any(k in t for k in ("поиск", "новости", "узнай", "погода", "курс", "цена"))

@retry(wait=wait_fixed(8), stop=stop_after_attempt(3))
async def gemini_reply(history: list, parts) -> str:
    chat = gemini_model.start_chat(history=history)
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(None, chat.send_message, parts)
    if not response.candidates:
        return "Google заблокировал ответ по политике безопасности."
    return response.text