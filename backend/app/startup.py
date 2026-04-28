from __future__ import annotations
import asyncio
import logging
from sqlalchemy import text
from app.database import engine, SessionLocal, Base
from app.config import settings

logger = logging.getLogger(__name__)


async def run_startup():
    await _wait_for_db()
    await _create_tables()
    await _ensure_admin()
    await _check_redis()


async def _wait_for_db(retries: int = 10, delay: float = 2.0):
    for attempt in range(1, retries + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Database connected")
            return
        except Exception as exc:
            logger.warning("DB not ready (%d/%d): %s", attempt, retries, exc)
            if attempt == retries:
                raise
            await asyncio.sleep(delay)


async def _create_tables():
    import app.models  # noqa: F401 — registers all models on Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tables OK")


async def _ensure_admin():
    from sqlalchemy import or_, select
    from sqlalchemy.exc import IntegrityError

    from app.models.user import User
    from app.services.crypto import hash_password

    async with SessionLocal() as db:
        result = await db.execute(
            select(User)
            .where(
                or_(
                    User.role == "admin",
                    User.username == settings.admin_username,
                )
            )
            .limit(1)
        )
        if result.scalar_one_or_none():
            return

        admin = User(
            username=settings.admin_username,
            password_hash=hash_password(settings.admin_password),
            role="admin",
        )
        db.add(admin)
        try:
            await db.commit()
            logger.info("Created initial admin: %s", settings.admin_username)
        except IntegrityError:
            await db.rollback()
            logger.info(
                "Initial admin already exists (parallel workers or existing DB): %s",
                settings.admin_username,
            )


async def _check_redis():
    import redis.asyncio as aioredis
    from app.config import settings

    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    await client.ping()
    await client.aclose()
    logger.info("Redis OK")
