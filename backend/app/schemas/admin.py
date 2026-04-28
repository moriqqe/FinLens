from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, field_validator


class AdminUserOut(BaseModel):
    id: uuid.UUID
    username: str
    role: str
    is_active: bool
    use_admin_key: bool
    has_api_key: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None

    model_config = {"from_attributes": True}


class ResetPasswordRequest(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not 8 <= len(v) <= 128:
            raise ValueError("Password must be 8-128 characters")
        return v


class GlobalKeyRequest(BaseModel):
    api_key: str


class RegistrationToggleRequest(BaseModel):
    open: bool


class StatsOut(BaseModel):
    total_users: int
    active_users: int
    total_uploads: int


class AuditLogOut(BaseModel):
    id: int
    user_id: Optional[uuid.UUID] = None
    action: str
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}
