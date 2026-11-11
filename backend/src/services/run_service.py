"""归并运行服务：校窗口 → 建 run → 投递 Celery → 查询结果与幂等标记。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.config.celery_app import TASK_MERGE_RUN, celery_app
from src.constants import error_codes as codes
from src.constants.enums import RunStatus, StreamStatus
from src.constants.limits import MAX_WINDOW_EVENTS
from src.models.cdc_event import CdcEvent
from src.models.change_stream import ChangeStream
from src.models.merge_run import MergeRun
from src.models.merge_target import MergeTarget
from src.schemas.run import serialize_run
from src.utils.errors import AppError, not_found
from src.utils.logger import get_logger
from src.utils.lsn import LsnWindow, normalize_window

logger = get_logger("cdcmerge.runs")


def create_run(
    db: Session,
    stream_id: str,
    window_start_lsn: int | None,
    window_end_lsn: int | None,
    triggered_by: str | None,
) -> MergeRun:
    stream = db.get(ChangeStream, stream_id)
    if stream is None:
        raise not_found("ChangeStream", stream_id)
    if stream.status == StreamStatus.PAUSED.value:
        raise AppError(codes.STREAM_PAUSED, "变更流已暂停，不能发起归并", f"stream={stream.name}")

    active = (
        db.query(MergeRun)
        .filter(
            MergeRun.stream_id == stream.id,
            MergeRun.status.in_([RunStatus.QUEUED.value, RunStatus.RUNNING.value]),
        )
        .one_or_none()
    )
    if active is not None:
        raise AppError(
            codes.RUN_ALREADY_ACTIVE,
            "该流已有进行中的归并运行",
            f"run_id={active.id} status={active.status}",
        )

    window = normalize_window(window_start_lsn, window_end_lsn, int(stream.watermark_lsn), int(stream.max_lsn))
    if window.end < window.start:
        raise AppError(
            codes.WATERMARK_INVALID,
            "窗口结束 LSN 小于起始 LSN",
            f"window=[{window.start},{window.end}]",
        )

    event_count = (
        db.query(func.count(CdcEvent.id))
        .filter(
            CdcEvent.stream_id == stream.id,
            CdcEvent.lsn >= window.start,
            CdcEvent.lsn <= window.end,
        )
        .scalar()
        or 0
    )
    if event_count == 0:
        raise AppError(
            codes.WINDOW_EMPTY,
            "窗口内没有事件，无法归并",
            f"window=[{window.start},{window.end}]",
        )
    if event_count > MAX_WINDOW_EVENTS:
        raise AppError(
            codes.WINDOW_TOO_LARGE,
            "窗口事件数超出上限，请缩小 LSN 区间",
            f"count={event_count} max={MAX_WINDOW_EVENTS}",
        )

    target = _match_target(db, stream)
    run = MergeRun(
        stream_id=stream.id,
        target_id=target.id if target else None,
        window_start_lsn=window.start,
        window_end_lsn=window.end,
        status=RunStatus.QUEUED.value,
        triggered_by=triggered_by,
        watermark_before=int(stream.watermark_lsn),
        received_count=0,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        result = celery_app.send_task(TASK_MERGE_RUN, args=[str(run.id)])
        run.celery_task_id = result.id
        db.commit()
        logger.info("enqueued merge run=%s task=%s window=%s", run.id, result.id, window.as_dict())
    except Exception as exc:  # noqa: BLE001 - Broker 异常要落库成 failed，而不是 500
        run.status = RunStatus.FAILED.value
        run.error_message = f"任务投递失败：{exc}"[:600]
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        logger.warning("enqueue failed run=%s error=%s", run.id, exc)

    return run


def _match_target(db: Session, stream: ChangeStream) -> MergeTarget | None:
    candidate = db.query(MergeTarget).filter(MergeTarget.name == f"{stream.name}_dw").one_or_none()
    if candidate is not None:
        return candidate
    return db.query(MergeTarget).order_by(MergeTarget.created_at.asc()).first()


def list_runs(db: Session, stream_id: str | None = None, limit: int = 30) -> dict[str, Any]:
    q = db.query(MergeRun).order_by(MergeRun.created_at.desc())
    if stream_id:
        q = q.filter(MergeRun.stream_id == stream_id)
    rows = q.limit(limit).all()
    names = _stream_names(db)
    return {"items": [_serialize(db, row, names) for row in rows], "total": len(rows)}


def get_run(db: Session, run_id: str) -> MergeRun:
    run = db.get(MergeRun, run_id)
    if run is None:
        raise not_found("MergeRun", run_id)
    return run


def run_detail(db: Session, run_id: str) -> dict[str, Any]:
    run = get_run(db, run_id)
    names = _stream_names(db)
    payload = _serialize(db, run, names)
    payload["result"] = run.result_json
    return payload


def _serialize(db: Session, run: MergeRun, names: dict[str, str]) -> dict[str, Any]:
    from src.schemas.run import serialize_run

    idempotent = None
    if run.status == RunStatus.SUCCEEDED.value and run.result_digest:
        twin = (
            db.query(MergeRun)
            .filter(
                MergeRun.stream_id == run.stream_id,
                MergeRun.window_start_lsn == run.window_start_lsn,
                MergeRun.window_end_lsn == run.window_end_lsn,
                MergeRun.result_digest == run.result_digest,
                MergeRun.status == RunStatus.SUCCEEDED.value,
                MergeRun.id != run.id,
            )
            .order_by(MergeRun.created_at.asc())
            .first()
        )
        idempotent = twin is not None
    return serialize_run(run, names.get(str(run.stream_id)), idempotent)


def _stream_names(db: Session) -> dict[str, str]:
    return {str(row.id): row.name for row in db.query(ChangeStream).all()}


def stats(db: Session) -> dict[str, Any]:
    total = db.query(func.count(MergeRun.id)).scalar() or 0
    succeeded = (
        db.query(func.count(MergeRun.id)).filter(MergeRun.status == RunStatus.SUCCEEDED.value).scalar() or 0
    )
    avg_ms = (
        db.query(func.avg(MergeRun.duration_ms))
        .filter(MergeRun.status == RunStatus.SUCCEEDED.value)
        .scalar()
    )
    return {
        "total_runs": int(total),
        "succeeded_runs": int(succeeded),
        "avg_duration_ms": int(avg_ms) if avg_ms else 0,
    }
