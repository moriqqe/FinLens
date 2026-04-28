from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import SESSION_COOKIE, client_ip, cookie_secure, get_current_user
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, UserOut
from app.services import session as session_svc
from app.services.audit import log_action
from app.services.crypto import hash_password, mask_key, verify_password, decrypt
from app.services.rate_limit import login_rate_limit, register_rate_limit
from app.services.settings_store import get_setting_value

router = APIRouter()


@router.post("/register")
async def register(
    request: Request,
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    ip = client_ip(request)
    await register_rate_limit(ip)
    open_raw = await get_setting_value(db, "registration_open")
    if open_raw != "true":
        raise HTTPException(status_code=403, detail="Registration is currently closed")
    res = await db.execute(select(User).where(User.username == body.username))
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already taken")
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role="user",
    )
    db.add(user)
    await db.flush()
    await log_action(
        db,
        "register",
        user_id=user.id,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
        details={"username": body.username},
    )
    await db.commit()
    return {"ok": True}


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    ip = client_ip(request)
    ua = request.headers.get("user-agent", "")
    await login_rate_limit(ip)
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        await log_action(db, "login_failed", user_id=None, ip=ip, user_agent=ua, details={"username": body.username})
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    token = await session_svc.create_session(str(user.id), ip, ua)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=cookie_secure(request),
        samesite="strict",
        max_age=session_svc.SESSION_TTL,
        path="/",
    )

    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = ip
    await log_action(db, "login", user_id=user.id, ip=ip, user_agent=ua)
    await db.commit()
    return {"ok": True}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    token = request.cookies.get(SESSION_COOKIE)
    uid = None
    if token:
        raw = await session_svc.get_redis().get(f"session:{token}")
        if raw:
            import json
            from uuid import UUID

            uid_str = json.loads(raw).get("user_id")
            if uid_str:
                uid = UUID(uid_str)
        await session_svc.delete_session(token)
        if uid:
            await log_action(
                db,
                "logout",
                user_id=uid,
                ip=client_ip(request),
                user_agent=request.headers.get("user-agent"),
            )
            await db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    masked = None
    if user.api_key_encrypted:
        try:
            masked = mask_key(decrypt(user.api_key_encrypted))
        except Exception:
            masked = "sk-...****"
    return UserOut(
        id=user.id,
        username=user.username,
        role=user.role,
        use_admin_key=user.use_admin_key,
        has_api_key=bool(user.api_key_encrypted),
        api_key_masked=masked,
    )
