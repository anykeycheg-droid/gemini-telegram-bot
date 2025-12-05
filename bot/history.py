import asyncio
import pickle
import os
from typing import Dict, List, Any
import aioredis

# Пытаемся подключиться к Redis (Render даёт переменную REDIS_URL)
REDIS_URL = os.getenv("REDIS_URL") or os.getenv("REDIS_TLS_URL")
redis = None
if REDIS_URL:
    redis = aioredis.from_url(REDIS_URL, decode_responses=False, ssl=REDIS_URL.startswith("rediss://"))

HISTORY_FILE = "/data/history.pkl"  # Render даёт persistent /data

lock = asyncio.Lock()
_memory_cache: Dict[int, List[Dict[str, Any]]] = {}

async def get_history(user_id: int) -> List[Dict[str, Any]]:
    if redis:
        data = await redis.get(f"history:{user_id}")
        if data:
            return pickle.loads(data)
    else:
        async with lock:
            if user_id not in _memory_cache:
                if os.path.exists(HISTORY_FILE):
                    try:
                        with open(HISTORY_FILE, "rb") as f:
                            full = pickle.load(f)
                            _memory_cache.update(full)
                    except:
                        pass
            return _memory_cache.get(user_id, []).copy()
    return _memory_cache.get(user_id, []).copy()

async def save_history(user_id: int):
    hist = _memory_cache.get(user_id, [])
    if len(hist) > 80:  # обрезаем старую историю
        hist[:] = hist[-80:]

    if redis:
        await redis.setex(f"history:{user_id}", 60*60*24*30, pickle.dumps(hist))  # 30 дней
    else:
        async with lock:
            _memory_cache[user_id] = hist
            try:
                os.makedirs("/data", exist_ok=True)
                with open(HISTORY_FILE, "wb") as f:
                    pickle.dump(_memory_cache, f)
            except Exception as e:
                print("Не удалось сохранить историю на диск:", e)

async def clear_all_history():
    if  # для админских нужд
    if redis:
        keys = await redis.keys("history:*")
        if keys:
            await redis.delete(*keys)
    else:
        async with lock:
            _memory_cache.clear()
            if os.path.exists(HISTORY_FILE):
                os.unlink(HISTORY_FILE)