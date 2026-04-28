from __future__ import annotations
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import client_ip, require_admin
from app.models.audit_log import AuditLog
from app.models.upload import Upload
from app.models.user import User
from app.schemas.admin import (
    AdminUserOut,
    AuditLogOut,
    GlobalKeyRequest,
    RegistrationToggleRequest,
    ResetPasswordRequest,
    StatsOut,
)
from app.services.audit import log_action
from app.services.crypto import encrypt, hash_password
from app.services.settings_store import set_setting_value


router = APIRouter()


def user_to_admin_out(u: User) -> AdminUserOut:
    return AdminUserOut(
        id=u.id,
        username=u.username,
        role=u.role,
        is_active=u.is_active,
        use_admin_key=u.use_admin_key,
        has_api_key=bool(u.api_key_encrypted),
        created_at=u.created_at,
        last_login_at=u.last_login_at,
        last_login_ip=str(u.last_login_ip) if u.last_login_ip is not None else None,
    )


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return [user_to_admin_out(u) for u in result.scalars().all()]


@router.post("/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot toggle your own account")
    row = await db.execute(select(User).where(User.id == user_id))
    user = row.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = not user.is_active
    await log_action(
        db,
        "admin_toggle_active",
        user_id=admin.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={"target": str(user_id), "is_active": user.is_active},
    )
    await db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/reset-password")
async def admin_reset_password(
    user_id: uuid.UUID,
    body: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    row = await db.execute(select(User).where(User.id == user_id))
    user = row.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = hash_password(body.new_password)
    await log_action(
        db,
        "admin_reset_password",
        user_id=admin.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={"target": str(user_id)},
    )
    await db.commit()
    return {"ok": True}


@router.delete("/users/{user_id}")
async def admin_delete_user(
    user_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    row = await db.execute(select(User).where(User.id == user_id))
    user = row.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await log_action(
        db,
        "admin_delete_user",
        user_id=admin.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={"target": str(user_id)},
    )
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/toggle-admin-key")
async def toggle_user_admin_key(
    user_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    row = await db.execute(select(User).where(User.id == user_id))
    user = row.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.use_admin_key = not user.use_admin_key
    await log_action(
        db,
        "admin_toggle_admin_key",
        user_id=admin.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={"target": str(user_id), "use_admin_key": user.use_admin_key},
    )
    await db.commit()
    return {"ok": True}


@router.post("/global-key")
async def set_global_key(
    body: GlobalKeyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    enc = encrypt(body.api_key.strip())
    await set_setting_value(db, "admin_key_encrypted", enc)
    await log_action(
        db,
        "admin_global_key_set",
        user_id=admin.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    return {"ok": True}


@router.delete("/global-key")
async def delete_global_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    await set_setting_value(db, "admin_key_encrypted", "")
    await log_action(
        db,
        "admin_global_key_delete",
        user_id=admin.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    return {"ok": True}


@router.get("/logs", response_model=list[AuditLogOut])
async def list_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user_id: Optional[uuid.UUID] = Query(None),
    action: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    q = select(AuditLog).order_by(AuditLog.created_at.desc())
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
    if action:
        q = q.where(AuditLog.action == action)
    q = q.offset((page - 1) * limit).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


@router.get("/stats", response_model=StatsOut)
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    total_users = int(await db.scalar(select(func.count()).select_from(User)) or 0)
    active_users = int(
        await db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0
    )
    total_uploads = int(await db.scalar(select(func.count()).select_from(Upload)) or 0)
    return StatsOut(
        total_users=total_users,
        active_users=active_users,
        total_uploads=total_uploads,
    )


@router.post("/settings/registration")
async def set_registration_open(
    body: RegistrationToggleRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    await set_setting_value(db, "registration_open", "true" if body.open else "false")
    await log_action(
        db,
        "admin_registration_setting",
        user_id=admin.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={"open": body.open},
    )
    await db.commit()
    return {"ok": True}
