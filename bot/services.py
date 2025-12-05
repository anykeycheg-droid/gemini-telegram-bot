import asyncio
import logging
from typing import List, Dict, Any
from tenacity import retry, wait_exponential, stop_after_attempt

try:
    # Пробуем новую SDK (рекомендуемая на 2025)
    from google.genai import GenerativeModel, configure
    NEW_SDK = True
    configure(api_key=settings.gemini_api_key.get_secret_value())
    model = GenerativeModel(
        "gemini-2.0-flash",
        system_instruction="Ты — остроумный помощник в Telegram. Отвечай кратко, по-русски, с юмором."
    )
    search_model = GenerativeModel("gemini-2.0-flash")
except ImportError:
    # Fallback на старую SDK (если Render не обновил)
    NEW_SDK = False
    import google.generativeai as genai
    genai.configure(api_key=settings.gemini_api_key.get_secret_value())
    model = genai.GenerativeModel("gemini-2.0-flash")
    search_model = genai.GenerativeModel("gemini-2.0-flash")

log = logging.getLogger(__name__)
GEMINI_SEMAPHORE = asyncio.Semaphore(10)

async def should_use_search(text: str) -> bool:
    prompt = f"Ответь только YES или NO: нужно ли гуглить для ответа?\n\n{text}"
    try:
        async with GEMINI_SEMAPHORE:
            if NEW_SDK:
                response = await search_model.generate_content_async(prompt, config={"temperature": 0, "max_output_tokens": 3})
            else:
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(None, lambda: search_model.generate_content(prompt, generation_config=genai.types.GenerationConfig(temperature=0, max_output_tokens=3)))
            return "YES" in response.text.strip().upper()
    except Exception as e:
        log.warning(f"Search decision error: {e}")
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
        chat_history = history[-40:]
        if NEW_SDK:
            chat = model.start_chat(history=chat_history)
            response = await chat.send_message_async("")
        else:
            # Fallback для старой SDK: system_prompt в начало истории
            system_prompt = "Ты — остроумный помощник в Telegram. Отвечай кратко, по-русски, с юмором."
            full_history = [{"role": "model", "parts": [system_prompt]}] + chat_history
            chat = model.start_chat(history=full_history)
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, lambda: chat.send_message(""))
        if not response.candidates:
            return "Ответ заблокирован по правилам безопасности."
        return response.text