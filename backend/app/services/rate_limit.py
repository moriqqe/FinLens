from __future__ import annotations
from fastapi import HTTPException
from app.services.session import get_redis


async def check_rate_limit(key: str, limit: int, window: int, block_for: int = 0):
    r = get_redis()
    current = await r.incr(key)
    if current == 1:
        await r.expire(key, window)
    if current > limit:
        if block_for:
            await r.expire(key, block_for)
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")


async def login_rate_limit(ip: str):
    await check_rate_limit(f"rl:login:{ip}", limit=10, window=900, block_for=1800)


async def register_rate_limit(ip: str):
    await check_rate_limit(f"rl:register:{ip}", limit=5, window=3600)


async def upload_rate_limit(user_id: str):
    await check_rate_limit(f"rl:upload:{user_id}", limit=20, window=3600)


async def gpt_rate_limit(user_id: str):
    await check_rate_limit(f"rl:gpt:{user_id}", limit=50, window=86400)
