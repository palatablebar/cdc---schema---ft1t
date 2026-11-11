"""RBAC 角色常量。前后端必须一致：users.role / constants/roles.py / frontend/constants/roles.ts / <RequireRole>。"""
from __future__ import annotations

ROLE_ADMIN = "admin"
ROLE_ENGINEER = "engineer"
ROLE_VIEWER = "viewer"

ALL_ROLES: tuple[str, ...] = (ROLE_ADMIN, ROLE_ENGINEER, ROLE_VIEWER)

# 能力矩阵：action -> 允许的角色
PERMISSIONS: dict[str, tuple[str, ...]] = {
    "streams:read": ALL_ROLES,
    "streams:write": (ROLE_ADMIN,),
    "streams:reset_watermark": (ROLE_ADMIN,),
    "events:read": ALL_ROLES,
    "runs:read": ALL_ROLES,
    "runs:trigger": (ROLE_ADMIN, ROLE_ENGINEER),
    "rejected:read": ALL_ROLES,
    "rejected:replay": (ROLE_ADMIN, ROLE_ENGINEER),
    "schema:read": ALL_ROLES,
    "schema:write": (ROLE_ADMIN, ROLE_ENGINEER),
    "audit:read": ALL_ROLES,
    "users:admin": (ROLE_ADMIN,),
}


def role_can(role: str, action: str) -> bool:
    return role in PERMISSIONS.get(action, ())


ROLE_LABELS = {ROLE_ADMIN: "平台管理员", ROLE_ENGINEER: "数据工程师", ROLE_VIEWER: "分析师"}


def role_permissions(role: str) -> list[str]:
    return [action for action, roles in PERMISSIONS.items() if role in roles]
