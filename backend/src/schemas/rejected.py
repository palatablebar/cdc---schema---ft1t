from __future__ import annotations

from typing import Any


def serialize_rejected(row: Any, stream_name: str | None = None) -> dict[str, Any]:
    from src.constants.enums import ENUM_LABELS
    from src.utils.formatters import format_lsn, iso

    return {
        "id": str(row.id),
        "event_id": str(row.event_id) if row.event_id else None,
        "run_id": str(row.run_id) if row.run_id else None,
        "stream_id": str(row.stream_id),
        "stream_name": stream_name,
        "lsn": row.lsn,
        "lsn_display": format_lsn(row.lsn),
        "reason": row.reason,
        "reason_label": ENUM_LABELS["RejectReason"].get(row.reason, row.reason),
        "detail": row.detail,
        "payload": row.payload_json,
        "status": row.status,
        "status_label": ENUM_LABELS["RejectStatus"].get(row.status, row.status),
        "replayed_event_id": str(row.replayed_event_id) if row.replayed_event_id else None,
        "created_at": iso(row.created_at),
        "resolved_at": iso(row.resolved_at),
    }
