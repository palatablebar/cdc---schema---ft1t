"""认证服务：登录、刷新、口令校验。"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from src.constants import error_codes as codes
from src.constants.roles import role_permissions
from src.models.user import User
from src.utils.errors import AppError
from src.utils.jwt import create_access_token, create_refresh_token, decode_token
from src.utils.password import verify_password


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.query(User).filter(User.email == email.lower().strip()).one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise AppError(codes.AUTH_INVALID, "邮箱或密码不正确", f"email={email}")
    if not user.is_active:
        raise AppError(codes.FORBIDDEN, "账号已停用", f"user_id={user.id}")
    return user


def issue_tokens(user: User) -> dict[str, Any]:
    return {
        "access_token": create_access_token(str(user.id), user.role, user.email),
        "refresh_token": create_refresh_token(str(user.id), user.role, user.email),
        "token_type": "bearer",
        "expires_in": 7200,
    }


def refresh(db: Session, refresh_token: str) -> dict[str, Any]:
    payload = decode_token(refresh_token, expected_type="refresh")
    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise AppError(codes.AUTH_INVALID, "账号不可用", "refresh token user missing")
    return issue_tokens(user)


def capabilities(user: User) -> dict[str, Any]:
    return {"role": user.role, "permissions": role_permissions(user.role)}
