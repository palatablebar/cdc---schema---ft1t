from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RunCreateRequest(BaseModel):
    stream_id: str
    window_start_lsn: int | None = Field(default=None, ge=1)
    window_end_lsn: int | None = Field(default=None, ge=1)
    note: str = ""


def serialize_run(run: Any, stream_name: str | None = None, idempotent: bool | None = None) -> dict[str, Any]:
    from src.constants.enums import ENUM_LABELS
    from src.utils.formatters import format_lsn, iso

    payload = {
        "id": str(run.id),
        "stream_id": str(run.stream_id),
        "stream_name": stream_name,
        "window_start_lsn": run.window_start_lsn,
        "window_end_lsn": run.window_end_lsn,
        "window_display": f"{format_lsn(run.window_start_lsn)} - {format_lsn(run.window_end_lsn)}",
        "status": run.status,
        "status_label": ENUM_LABELS["RunStatus"].get(run.status, run.status),
        "received_count": run.received_count,
        "processed_count": run.processed_count,
        "duplicate_count": run.duplicate_count,
        "rejected_count": run.rejected_count,
        "inserted_count": run.inserted_count,
        "updated_count": run.updated_count,
        "deleted_count": run.deleted_count,
        "upserted_count": run.upserted_count,
        "watermark_before": run.watermark_before,
        "watermark_after": run.watermark_after,
        "watermark_after_display": format_lsn(run.watermark_after),
        "duration_ms": run.duration_ms,
        "result_digest": run.result_digest,
        "error_message": run.error_message,
        "created_at": iso(run.created_at),
        "started_at": iso(run.started_at),
        "finished_at": iso(run.finished_at),
    }
    if idempotent is not None:
        payload["idempotent"] = idempotent
    return payload
