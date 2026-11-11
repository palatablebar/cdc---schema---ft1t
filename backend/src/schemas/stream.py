from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class StreamCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    source_db: str = Field(min_length=1, max_length=120)
    source_table: str = Field(min_length=1, max_length=160)
    pk_column: str = Field(default="id", min_length=1, max_length=80)
    description: str = ""
    owner_team: str = ""


class StreamUpdateRequest(BaseModel):
    status: str | None = None
    description: str | None = None
    reset_watermark: int | None = Field(default=None, ge=0)


def serialize_stream(stream: Any, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    from src.constants.enums import ENUM_LABELS
    from src.utils.formatters import format_lsn, iso

    payload = {
        "id": str(stream.id),
        "name": stream.name,
        "source_db": stream.source_db,
        "source_table": stream.source_table,
        "pk_column": stream.pk_column,
        "watermark_lsn": stream.watermark_lsn,
        "watermark_display": format_lsn(stream.watermark_lsn),
        "max_lsn": stream.max_lsn,
        "max_lsn_display": format_lsn(stream.max_lsn),
        "lag": max(0, int(stream.max_lsn) - int(stream.watermark_lsn)),
        "status": stream.status,
        "status_label": ENUM_LABELS["StreamStatus"].get(stream.status, stream.status),
        "description": stream.description,
        "owner_team": stream.owner_team,
        "last_event_at": iso(stream.last_event_at),
        "created_at": iso(stream.created_at),
    }
    if summary is not None:
        payload["summary"] = summary
    return payload


def serialize_event(event: Any, redact: bool = False) -> dict[str, Any]:
    from src.constants.enums import ENUM_LABELS
    from src.utils.formatters import format_lsn, iso

    return {
        "id": str(event.id),
        "stream_id": str(event.stream_id),
        "lsn": event.lsn,
        "lsn_display": format_lsn(event.lsn),
        "received_seq": event.received_seq,
        "op": event.op,
        "op_label": ENUM_LABELS["CdcOp"].get(event.op, event.op),
        "pk_value": event.pk_value,
        "before": event.before_json,
        "after": event.after_json,
        "reject_reason": event.reject_reason,
        "reject_reason_label": ENUM_LABELS["RejectReason"].get(event.reject_reason, "")
        if event.reject_reason
        else None,
        "reject_detail": event.reject_detail,
        "replayed_from_id": str(event.replayed_from_id) if event.replayed_from_id else None,
        "received_at": iso(event.received_at),
    }
