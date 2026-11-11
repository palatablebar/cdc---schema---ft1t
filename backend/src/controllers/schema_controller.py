"""schema 演进 controller。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.models.user import User
from src.schemas.schema_diff import SchemaDiffRequest
from src.services import audit_service, schema_service, stream_service


def list_versions(stream_id: str, db: Session) -> dict:
    stream_service.get_stream(db, stream_id)
    return schema_service.list_versions(db, stream_id) | {
        "pairs": schema_service.version_compare_pairs(db, stream_id)
    }


def diff_versions(request: Request, payload: SchemaDiffRequest, user: User, db: Session) -> dict:
    result = schema_service.diff(db, payload.left_version_id, payload.right_version_id)
    audit_service.record(
        db,
        action="schema.diff",
        entity_type="SchemaVersion",
        entity_id=f"{payload.left_version_id}->{payload.right_version_id}",
        actor_id=str(user.id),
        payload={
            "compat_level": result["compat_level"],
            "change_count": len(result["changes"]),
        },
        ip=getattr(request.state, "client_ip", None),
        trace_id=getattr(request.state, "trace_id", None),
    )
    return result
