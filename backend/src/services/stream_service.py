"""变更流服务：列表/详情/创建/状态与水位置操作 + 看板统计。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.constants import error_codes as codes
from src.constants.enums import CdcOp, RejectStatus, RunStatus, StreamStatus
from src.models.cdc_event import CdcEvent
from src.models.change_stream import ChangeStream
from src.models.merge_run import MergeRun as MergeRunModel
from src.models.rejected_event import RejectedEvent
from src.schemas.stream import StreamCreateRequest
from src.utils.errors import AppError, not_found


def list_streams(db: Session) -> list[dict[str, Any]]:
    from src.schemas.stream import serialize_stream

    streams = db.query(ChangeStream).order_by(ChangeStream.created_at.asc()).all()
    result = []
    for stream in streams:
        result.append(serialize_stream(stream, summary(db, stream)))
    return result


def summary(db: Session, stream: ChangeStream) -> dict[str, Any]:
    """看板需要的三个聚合：事件按 op 计数、待处理拒绝数、最近一次运行。"""
    op_rows = (
        db.query(CdcEvent.op, func.count(CdcEvent.id))
        .filter(CdcEvent.stream_id == stream.id)
        .group_by(CdcEvent.op)
        .all()
    )
    by_op = {row[0]: int(row[1]) for row in op_rows}
    pending_rejected = (
        db.query(func.count(RejectedEvent.id))
        .filter(
            RejectedEvent.stream_id == stream.id,
            RejectedEvent.status == RejectStatus.PENDING.value,
        )
        .scalar()
        or 0
    )
    last_run = (
        db.query(MergeRunModel)
        .filter(MergeRunModel.stream_id == stream.id)
        .order_by(MergeRunModel.created_at.desc())
        .first()
    )
    total_events = (
        db.query(func.count(CdcEvent.id)).filter(CdcEvent.stream_id == stream.id).scalar() or 0
    )
    return {
        "event_total": int(total_events),
        "by_op": {
            "insert": by_op.get(CdcOp.INSERT.value, 0),
            "update": by_op.get(CdcOp.UPDATE.value, 0),
            "delete": by_op.get(CdcOp.DELETE.value, 0),
        },
        "pending_rejected": int(pending_rejected),
        "last_run": {
            "id": str(last_run.id),
            "status": last_run.status,
            "upserted_count": last_run.upserted_count,
            "finished_at": last_run.finished_at.isoformat() if last_run.finished_at else None,
        }
        if last_run
        else None,
    }


def get_stream(db: Session, stream_id: str) -> ChangeStream:
    stream = db.get(ChangeStream, stream_id)
    if stream is None:
        raise not_found("ChangeStream", stream_id)
    return stream


def create_stream(db: Session, payload: StreamCreateRequest) -> ChangeStream:
    exists = db.query(ChangeStream).filter(ChangeStream.name == payload.name).one_or_none()
    if exists is not None:
        raise AppError(codes.VALIDATION_ERROR, "变更流名称已存在", f"name={payload.name}")
    stream = ChangeStream(
        name=payload.name,
        source_db=payload.source_db,
        source_table=payload.source_table,
        pk_column=payload.pk_column,
        description=payload.description,
        owner_team=payload.owner_team,
        watermark_lsn=0,
        max_lsn=0,
        status=StreamStatus.HEALTHY.value,
    )
    db.add(stream)
    db.commit()
    db.refresh(stream)
    return stream


def update_stream(
    db: Session,
    stream_id: str,
    status: str | None,
    description: str | None,
    reset_watermark: int | None,
) -> ChangeStream:
    stream = get_stream(db, stream_id)
    if status is not None:
        if status not in StreamStatus.values():
            raise AppError(codes.VALIDATION_ERROR, "状态取值不合法", f"status={status}")
        stream.status = status
    if description is not None:
        stream.description = description
    if reset_watermark is not None:
        if reset_watermark > stream.max_lsn:
            raise AppError(
                codes.WATERMARK_INVALID,
                "水位线不能超过最新 LSN",
                f"reset={reset_watermark} max_lsn={stream.max_lsn}",
            )
        stream.watermark_lsn = reset_watermark
    db.commit()
    db.refresh(stream)
    return stream


def board(db: Session) -> dict[str, Any]:
    """事件流看板汇总：流数、事件总数、待处理拒绝、最近运行。"""
    from src.models.merge_run import MergeRun as RunModel

    streams = list_streams(db)
    total_events = db.query(func.count(CdcEvent.id)).scalar() or 0
    pending = (
        db.query(func.count(RejectedEvent.id))
        .filter(RejectedEvent.status == RejectStatus.PENDING.value)
        .scalar()
        or 0
    )
    active_runs = (
        db.query(func.count(RunModel.id))
        .filter(RunModel.status.in_([RunStatus.QUEUED.value, RunStatus.RUNNING.value]))
        .scalar()
        or 0
    )
    succeeded = (
        db.query(func.count(RunModel.id))
        .filter(RunModel.status == RunStatus.SUCCEEDED.value)
        .scalar()
        or 0
    )
    return {
        "streams": streams,
        "totals": {
            "stream_count": len(streams),
            "event_count": int(total_events),
            "pending_rejected": int(pending),
            "active_runs": int(active_runs),
            "succeeded_runs": int(succeeded),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
