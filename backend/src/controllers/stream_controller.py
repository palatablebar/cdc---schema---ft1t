"""变更流 controller。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.constants.enums import ActorKind
from src.models.user import User
from src.schemas.event import EventQuery
from src.schemas.stream import StreamCreateRequest, StreamUpdateRequest, serialize_stream
from src.services import audit_service, event_service, stream_service


def list_streams(db: Session) -> dict:
    return {"items": stream_service.list_streams(db)}


def get_stream(stream_id: str, db: Session) -> dict:
    stream = stream_service.get_stream(db, stream_id)
    return serialize_stream(stream, stream_service.summary(db, stream))


def create_stream(request: Request, payload: StreamCreateRequest, user: User, db: Session) -> dict:
    stream = stream_service.create_stream(db, payload)
    audit_service.record(
        db,
        action="stream.create",
        entity_type="ChangeStream",
        entity_id=str(stream.id),
        actor_id=str(user.id),
        payload={"name": stream.name, "table": stream.source_table},
        ip=getattr(request.state, "client_ip", None),
        trace_id=getattr(request.state, "trace_id", None),
    )
    return serialize_stream(stream, stream_service.summary(db, stream))


def update_stream(
    request: Request,
    stream_id: str,
    payload: StreamUpdateRequest,
    user: User,
    db: Session,
) -> dict:
    stream = stream_service.update_stream(
        db, stream_id, payload.status, payload.description, payload.reset_watermark
    )
    audit_service.record(
        db,
        action="stream.update",
        entity_type="ChangeStream",
        entity_id=str(stream.id),
        actor_id=str(user.id),
        payload=payload.model_dump(exclude_none=True),
        ip=getattr(request.state, "client_ip", None),
        trace_id=getattr(request.state, "trace_id", None),
    )
    return serialize_stream(stream, stream_service.summary(db, stream))


def list_events(stream_id: str, query: EventQuery, db: Session) -> dict:
    stream_service.get_stream(db, stream_id)
    return event_service.list_events(db, stream_id, query)


def arrival_stats(stream_id: str, db: Session) -> dict:
    stream_service.get_stream(db, stream_id)
    return event_service.arrival_order_stats(db, stream_id)


def board(db: Session) -> dict:
    return stream_service.board(db)
