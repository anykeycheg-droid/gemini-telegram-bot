import aiohttp
import google.generativeai as genai
import asyncio
from typing import List, Dict, Any, Union
from .config import settings
from tenacity import retry, wait_exponential, stop_after_attempt
import logging

log = logging.getLogger(__name__)

# Настраиваем Gemini
genai.configure(api_key=settings.gemini_api_key.get_secret_value())

# Основная модель для ответов (system_instruction добавляем в generate_content)
main_model = genai.GenerativeModel("gemini-2.0-flash-exp")

# Лёгкая модель только для решения: нужен ли поиск?
search_decision_model = genai.GenerativeModel("gemini-2.0-flash-exp")

# Семфор для ограничения одновременных запросов к Gemini (чтобы не словить 429)
GEMINI_SEMAPHORE = asyncio.Semaphore(8)

async def google_search(query: str, num: int = 3) -> str:
    """Поиск в Google Custom Search (если ключи настроены)"""
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

async def should_use_search(user_message: str) -> bool:
    """Спрашиваем у самой модели — нужен ли поиск в интернете"""
    prompt = f"""Ответь только YES или NO.
Нужно ли искать актуальную информацию в интернете (новости, погода, курсы валют, цены, события после 2024 года) 
для точного ответа на вопрос:

"{user_message}"

Ответ: """
    try:
        async with GEMINI_SEMAPHORE:
            # Используем sync generate_content с executor для совместимости
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: search_decision_model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.0, max_output_tokens=5
                    )
                )
            )
            return "YES" in response.text.strip().upper()
    except Exception as e:
        log.warning(f"Ошибка при решении о поиске: {e}")
        return False

async def google_search(query: str, num: int = 4) -> str:
    """Опциональный поиск в Google через Custom Search JSON API"""
    if not settings.google_search_api_key or not settings.google_cse_id:
        return ""

    params = {
        "key": settings.google_search_api_key,
        "cx": settings.google_cse_id,
        "q": query,
        "num": num,
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.get("https://www.googleapis.com/customsearch/v1", params=params) as resp:
                if resp.status != 200:
                    return ""
                data = await resp.json()
                items = data.get("items", [])
                snippets = []
                for i, item in enumerate(items[:num], 1):
                    title = item.get("title", "")
                    snippet = item.get("snippet", "")
                    snippets.append(f"{i}. {title}\n{snippet}")
                return "\n\n".join(snippets) if snippets else ""
    except Exception as e:
        log.warning(f"Google search error: {e}")
        return ""
        
@retry(wait=wait_exponential(multiplier=1, min=4, max=15), stop=stop_after_attempt(4))
async def gemini_reply(history: List[Dict[str, Any]]) -> str:
    """Генерируем ответ с историей (история уже содержит последнее сообщение пользователя)"""
    async with GEMINI_SEMAPHORE:
        # Ограничиваем историю (20 пар = 40 сообщений)
        chat_history = history[-40:] if history else []
        chat = main_model.start_chat(history=chat_history)
        
        # Системный промпт (fallback для старых версий)
        system_prompt = "Ты — полезный и остроумный помощник в Telegram. Отвечай на русском языке, кратко и по делу."
        
        try:
            # Пробуем async метод (если версия поддерживает)
            response = await chat.send_message_async(system_prompt)
        except AttributeError:
            # Fallback на sync с executor
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, lambda: chat.send_message(system_prompt))
        
        if not response.candidates:
            return "Извини, Google заблокировал ответ по правилам безопасности."
        return response.text