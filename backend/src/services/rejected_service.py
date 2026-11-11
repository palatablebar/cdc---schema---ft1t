"""拒绝事件服务：列表 + 真实的重放修复（按原因走不同修复策略）。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.constants import error_codes as codes
from src.constants.enums import RejectStatus
from src.models.cdc_event import CdcEvent
from src.models.change_stream import ChangeStream
from src.models.rejected_event import RejectedEvent
from src.models.schema_version import SchemaVersion
from src.schemas.rejected import serialize_rejected
from src.utils.errors import AppError, not_found
from src.utils.payload_coerce import repair_payload


def list_rejected(
    db: Session,
    stream_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    q = db.query(RejectedEvent).order_by(RejectedEvent.created_at.desc())
    if stream_id:
        q = q.filter(RejectedEvent.stream_id == stream_id)
    if status:
        q = q.filter(RejectedEvent.status == status)
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    names = {str(row.id): row.name for row in db.query(ChangeStream).all()}
    return {
        "items": [serialize_rejected(row, names.get(str(row.stream_id))) for row in rows],
        "total": int(total),
        "offset": offset,
        "limit": limit,
    }


def counts(db: Session) -> dict[str, int]:
    rows = (
        db.query(RejectedEvent.reason, func.count(RejectedEvent.id))
        .filter(RejectedEvent.status == RejectStatus.PENDING.value)
        .group_by(RejectedEvent.reason)
        .all()
    )
    return {row[0]: int(row[1]) for row in rows}


def get_rejected(db: Session, rejected_id: str) -> RejectedEvent:
    row = db.get(RejectedEvent, rejected_id)
    if row is None:
        raise not_found("RejectedEvent", rejected_id)
    return row


def replay(db: Session, rejected_id: str) -> dict[str, Any]:
    row = get_rejected(db, rejected_id)
    if row.status != RejectStatus.PENDING.value:
        raise AppError(
            codes.REPLAY_ALREADY_DONE,
            "该事件已重放或已忽略",
            f"status={row.status}",
        )

    stream = db.get(ChangeStream, row.stream_id)
    if stream is None:
        raise not_found("ChangeStream", row.stream_id)

    latest = (
        db.query(SchemaVersion)
        .filter(SchemaVersion.stream_id == row.stream_id)
        .order_by(SchemaVersion.created_at.desc())
        .first()
    )
    fields = latest.fields_json if latest else []
    payload = row.payload_json or {}
    after = dict(payload.get("after") or {})

    repaired, note = repair_payload(row.reason, after, fields, stream.pk_column)
    if repaired is None:
        raise AppError(
            codes.REPLAY_NOT_POSSIBLE,
            f"该拒绝原因无法自动重放：{note}",
            f"reason={row.reason} detail={note}",
        )

    next_seq = (
        db.query(func.max(CdcEvent.received_seq))
        .filter(CdcEvent.stream_id == stream.id)
        .scalar()
        or 0
    ) + 1
    new_event = CdcEvent(
        stream_id=stream.id,
        lsn=row.lsn,
        received_seq=int(next_seq),
        op=payload.get("op") or "update",
        pk_value=str(repaired.get(stream.pk_column)),
        before_json=payload.get("before"),
        after_json=repaired,
        reject_reason=None,
        reject_detail=None,
        received_at=datetime.now(timezone.utc),
        replayed_from_id=row.event_id,
    )
    db.add(new_event)
    db.flush()

    row.status = RejectStatus.REPLAYED.value
    row.replayed_event_id = new_event.id
    row.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(new_event)

    return {
        "rejected": serialize_rejected(row, stream.name),
        "new_event_id": str(new_event.id),
        "repair_note": note,
        "schema_version": latest.version_label if latest else None,
    }


def dismiss(db: Session, rejected_id: str) -> dict[str, Any]:
    row = get_rejected(db, rejected_id)
    if row.status != RejectStatus.PENDING.value:
        raise AppError(codes.REPLAY_ALREADY_DONE, "该事件已重放或已忽略", f"status={row.status}")
    row.status = RejectStatus.DISMISSED.value
    row.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return serialize_rejected(row)
