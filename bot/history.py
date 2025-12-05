# bot/history.py
import asyncio
import pickle
import os
from typing import Dict, List, Any

# --------------------- Redis (если есть) ---------------------
try:
    import aioredis
    REDIS_URL = os.getenv("REDIS_URL") or os.getenv("REDIS_TLS_URL")
    if REDIS_URL:
        redis = aioredis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=False,   # будем сами pickle-ить
            ssl=REDIS_URL.startswith("rediss://")
        )
    else:
        redis = None
except Exception:  # если aioredis не установлен — просто отключаем
    redis = None

# --------------------- Файловый fallback ---------------------
HISTORY_FILE = "/data/history.pkl"  # на Render /data — persistent диск
_memory_cache: Dict[int, List[Any]] = {}
_lock = asyncio.Lock()


async def get_history(user_id: int) -> List[Any]:
    """Возвращает копию истории пользователя"""
    if redis:
        raw = await redis.get(f"history:{user_id}")
        if raw:
            return pickle.loads(raw)

    # Файловый режим
    async with _lock:
        if user_id not in _memory_cache and os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "rb") as f:
                    full_data = pickle.load(f)
                    _memory_cache.update(full_data)
            except Exception:
                pass
        return _memory_cache.get(user_id, []).copy()


async def save_history(user_id: int):
    """Сохраняет историю пользователя (Redis → файл)"""
    hist = _memory_cache.get(user_id, [])

    # Обрезаем до последних ~80 сообщений (40 пар)
    if len(hist) > 80:
        hist[:] = hist[-80:]

    _memory_cache[user_id] = hist

    if redis:
        try:
            await redis.setex(f"history:{user_id}", 60 * 60 * 24 * 30, pickle.dumps(hist))  # 30 дней
        except Exception:
            pass
    else:
        async with _lock:
            try:
                os.makedirs("/data", exist_ok=True)
                with open(HISTORY_FILE, "wb") as f:
                    pickle.dump(_memory_cache, f)
            except Exception as e:
                print("Не удалось сохранить историю на диск:", e)


async def clear_history(user_id: int):
    """Полная очистка истории конкретного пользователя"""
    if redis:
        await redis.delete(f"history:{user_id}")
    _memory_cache.pop(user_id, None)
    await save_history(user_id)  # чтобы файл тоже очистился