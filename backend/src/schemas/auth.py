from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # 用普通字符串而不是 EmailStr：演示域名 cdc.local 属于保留 TLD，
    # email-validator 会拒绝它，登录接口不该做可投递性校验。
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(min_length=1, max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str


def serialize_user(user: Any) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat()
        if isinstance(user.created_at, datetime)
        else user.created_at,
    }
