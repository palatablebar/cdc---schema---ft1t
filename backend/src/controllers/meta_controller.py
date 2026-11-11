"""元信息 controller：健康检查、看板汇总、枚举字典、审计日志。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config.database import engine
from src.constants.enums import ENUM_LABELS
from src.constants.roles import ALL_ROLES, ROLE_LABELS, PERMISSIONS
from src.services import audit_service, rejected_service, run_service, stream_service


def health(db: Session) -> dict[str, Any]:
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "cdcmerge-backend",
        "db": "ok" if db_ok else "down",
        "engine": str(engine.url).rsplit("@", 1)[-1],
    }


def board(db: Session) -> dict[str, Any]:
    payload = stream_service.board(db)
    payload["rejected_by_reason"] = rejected_service.counts(db)
    payload["run_stats"] = run_service.stats(db)
    return payload


def enums() -> dict[str, Any]:
    return {
        "labels": ENUM_LABELS,
        "roles": [{"value": role, "label": ROLE_LABELS.get(role, role)} for role in ALL_ROLES],
        "permissions": {action: list(roles) for action, roles in PERMISSIONS.items()},
    }


def audit_logs(db: Session, limit: int, offset: int, serialize: bool = True) -> dict[str, Any]:
    rows, total = audit_service.list_logs(db, limit=limit, offset=offset)
    items = [audit_service.serialize_audit(row) for row in rows] if serialize else []
    return {"items": items, "total": int(total), "offset": offset, "limit": limit}
