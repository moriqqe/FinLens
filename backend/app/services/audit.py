from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def log_action(
    db: AsyncSession,
    action: str,
    user_id: Optional[uuid.UUID] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[dict] = None,
):
    entry = AuditLog(
        user_id=user_id,
        action=action,
        ip=ip,
        user_agent=user_agent,
        details=details,
    )
    db.add(entry)
    await db.flush()
