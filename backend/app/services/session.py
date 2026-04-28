from __future__ import annotations
import json
import secrets
from datetime import datetime, timezone
import redis.asyncio as aioredis
from app.config import settings

SESSION_TTL = 7 * 24 * 3600
MAX_SESSIONS_PER_USER = 5
_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def create_session(user_id: str, ip: str, user_agent: str) -> str:
    r = get_redis()
    token = secrets.token_urlsafe(32)

    # Enforce max sessions per user
    user_sessions_key = f"user_sessions:{user_id}"
    sessions = await r.lrange(user_sessions_key, 0, -1)
    if len(sessions) >= MAX_SESSIONS_PER_USER:
        oldest = sessions[0]
        await r.delete(f"session:{oldest}")
        await r.lrem(user_sessions_key, 1, oldest)

    payload = json.dumps({
        "user_id": user_id,
        "ip": ip,
        "user_agent": user_agent,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    await r.set(f"session:{token}", payload, ex=SESSION_TTL)
    await r.rpush(user_sessions_key, token)
    await r.expire(user_sessions_key, SESSION_TTL)
    return token


async def get_session(token: str, ip: str, user_agent: str) -> dict | None:
    r = get_redis()
    raw = await r.get(f"session:{token}")
    if not raw:
        return None
    data = json.loads(raw)
    if data.get("ip") != ip or data.get("user_agent") != user_agent:
        await r.delete(f"session:{token}")
        return None
    await r.expire(f"session:{token}", SESSION_TTL)
    return data


async def delete_session(token: str):
    r = get_redis()
    raw = await r.get(f"session:{token}")
    if raw:
        data = json.loads(raw)
        user_id = data.get("user_id")
        if user_id:
            await r.lrem(f"user_sessions:{user_id}", 1, token)
    await r.delete(f"session:{token}")
