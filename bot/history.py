import asyncio
import pickle
import os
from typing import List, Any

import aioredis

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL не указан в переменных окружения!")

redis = aioredis.from_url(
    REDIS_URL,
    decode_responses=False,
    ssl=REDIS_URL.startswith("rediss://")
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