import asyncio
import pickle
import os
from typing import List, Any

import redis.asyncio as aioredis

REDIS_URL = os.getenv("REDIS_URL")

if not REDIS_URL:
    raise RuntimeError("Переменная REDIS_URL не найдена в настройках Render!")

# Для Upstash с TLS — используем ssl_cert_reqs=None (не проверяем сертификат)
redis = aioredis.from_url(
    REDIS_URL,
    decode_responses=False,
    ssl_cert_reqs=None  # ← Это решает проблему с 'ssl' keyword
)

_memory_cache: dict[int, List[Any]] = {}


async def get_history(user_id: int) -> List[Any]:
    raw = await redis.get(f"history:{user_id}")
    if raw:
        return pickle.loads(raw)
    return _memory_cache.get(user_id, []).copy()


async def save_history(user_id: int):
    hist = _memory_cache.get(user_id, [])
    if len(hist) > 80:
        hist = hist[-80:]
    _memory_cache[user_id] = hist
    await redis.setex(f"history:{user_id}", 60*60*24*30, pickle.dumps(hist))


async def clear_history(user_id: int):
    await redis.delete(f"history:{user_id}")
    _memory_cache.pop(user_id, None)