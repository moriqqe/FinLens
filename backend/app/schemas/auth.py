from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator
import re


class RegisterRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not 3 <= len(v) <= 30:
            raise ValueError("Username must be 3-30 characters")
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", v):
            raise ValueError("Username may only contain letters, digits, _ and -")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not 8 <= len(v) <= 128:
            raise ValueError("Password must be 8-128 characters")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    role: str
    use_admin_key: bool
    has_api_key: bool
    api_key_masked: Optional[str] = None

    model_config = {"from_attributes": True}


class ApiKeyRequest(BaseModel):
    api_key: str
