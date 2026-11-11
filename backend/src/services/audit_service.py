"""审计日志写入：controller 层在业务成功后显式调用。"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from src.constants.enums import ActorKind
from src.models.audit_log import AuditLog


def record(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: str | None,
    payload: dict[str, Any] | None = None,
    actor_id: str | None = None,
    actor_kind: str = ActorKind.USER.value,
    ip: str | None = None,
    trace_id: str | None = None,
) -> AuditLog:
    row = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload_json=payload or {},
        actor_id=actor_id,
        actor_kind=actor_kind,
        ip=ip,
        trace_id=trace_id,
    )
    db.add(row)
    db.commit()
    return row


def list_logs(db: Session, limit: int = 50, offset: int = 0) -> tuple[list[AuditLog], int]:
    query = db.query(AuditLog).order_by(AuditLog.created_at.desc())
    total = query.count()
    return query.offset(offset).limit(limit).all(), total


def serialize_audit(row: AuditLog) -> dict[str, Any]:
    from src.utils.formatters import iso

    return {
        "id": str(row.id),
        "action": row.action,
        "actor_id": str(row.actor_id) if row.actor_id else None,
        "actor_kind": row.actor_kind,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "payload": row.payload_json,
        "ip": row.ip,
        "trace_id": row.trace_id,
        "created_at": iso(row.created_at),
    }
