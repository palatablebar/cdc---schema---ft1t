"""拒绝事件 controller：列表 / 重放 / 忽略。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.constants.enums import ActorKind
from src.models.user import User
from src.services import audit_service, rejected_service


def list_rejected(stream_id: str | None, status: str | None, limit: int, offset: int, db: Session) -> dict:
    return rejected_service.list_rejected(db, stream_id=stream_id, status=status, limit=limit, offset=offset)


def replay(request: Request, rejected_id: str, user: User, db: Session) -> dict:
    result = rejected_service.replay(db, rejected_id)
    audit_service.record(
        db,
        action="rejected.replay",
        entity_type="RejectedEvent",
        entity_id=rejected_id,
        actor_id=str(user.id),
        payload={
            "new_event_id": result["new_event_id"],
            "repair_note": result["repair_note"],
        },
        ip=getattr(request.state, "client_ip", None),
        trace_id=getattr(request.state, "trace_id", None),
    )
    return result


def dismiss(request: Request, rejected_id: str, user: User, db: Session) -> dict:
    result = rejected_service.dismiss(db, rejected_id)
    audit_service.record(
        db,
        action="rejected.dismiss",
        entity_type="RejectedEvent",
        entity_id=rejected_id,
        actor_id=str(user.id),
        payload={"status": result["status"]},
        ip=getattr(request.state, "client_ip", None),
        trace_id=getattr(request.state, "trace_id", None),
    )
    return result
