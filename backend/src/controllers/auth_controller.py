"""认证 controller：登录 / 刷新 / me。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.constants.roles import ROLE_LABELS
from src.models.user import User
from src.schemas.auth import LoginRequest, RefreshRequest, serialize_user
from src.services import audit_service, auth_service


def login(request: Request, payload: LoginRequest, db: Session) -> dict:
    user = auth_service.authenticate(db, payload.email, payload.password)
    tokens = auth_service.issue_tokens(user)
    audit_service.record(
        db,
        action="auth.login",
        entity_type="User",
        entity_id=str(user.id),
        actor_id=str(user.id),
        payload={"role": user.role},
        ip=getattr(request.state, "client_ip", None),
        trace_id=getattr(request.state, "trace_id", None),
    )
    return {**tokens, "user": serialize_user(user)}


def refresh(payload: RefreshRequest, db: Session) -> dict:
    return auth_service.refresh(db, payload.refresh_token)


def me(user: User) -> dict:
    payload = serialize_user(user)
    payload["role_label"] = ROLE_LABELS.get(user.role, user.role)
    payload.update(auth_service.capabilities(user))
    return payload
