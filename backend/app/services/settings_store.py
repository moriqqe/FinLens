from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.setting import Setting


async def get_setting_value(db: AsyncSession, key: str) -> str | None:
    row = await db.execute(select(Setting).where(Setting.key == key))
    s = row.scalar_one_or_none()
    return s.value if s else None


async def set_setting_value(db: AsyncSession, key: str, value: str) -> None:
    row = await db.execute(select(Setting).where(Setting.key == key))
    s = row.scalar_one_or_none()
    if s:
        s.value = value
    else:
        db.add(Setting(key=key, value=value))
    await db.flush()
