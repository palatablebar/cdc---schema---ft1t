"""真实归并任务：backend 发起 → worker 在容器内跑算法 → 结果落库。

任务只依赖 backend 已定义好的模型与算法（同一份代码，避免两套实现漂移）：
  src.services.merge_engine.compute_merge 是纯函数，这里只负责取数、落账、推进水位线。
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func

from src.config.database import session_scope
from src.constants.enums import MergeStrategy, RejectStatus, RunStatus
from src.models.cdc_event import CdcEvent
from src.models.change_stream import ChangeStream
from src.models.merge_run import MergeRun
from src.models.merge_target import MergeTarget
from src.models.rejected_event import RejectedEvent
from src.services.merge_engine import compute_merge
from src.utils.logger import get_logger
from src.utils.redis_client import get_redis

from worker_src.config.celery_app import celery_app

logger = get_logger("cdcmerge.worker.merge")

TASK_NAME = "cdcmerge.merge_run"


def _progress(run_id: str, phase: str, detail: dict[str, Any] | None = None) -> None:
    try:
        import json

        get_redis().setex(
            f"cdcmerge:progress:{run_id}",
            3600,
            json.dumps({"phase": phase, "detail": detail or {}}, ensure_ascii=False),
        )
    except Exception:  # noqa: BLE001 - 进度非关键路径
        pass


@celery_app.task(name=TASK_NAME, bind=True)
def merge_run_task(self, run_id: str) -> dict[str, Any]:
    started = time.perf_counter()
    with session_scope() as db:
        run = db.get(MergeRun, run_id)
        if run is None:
            logger.warning("merge run not found run=%s", run_id)
            return {"run_id": run_id, "status": "missing"}

        if run.status in RunStatus.terminal():
            logger.info("merge run already terminal run=%s status=%s", run_id, run.status)
            return {"run_id": run_id, "status": run.status}

        run.status = RunStatus.RUNNING.value
        run.started_at = datetime.now(timezone.utc)
        db.commit()
        _progress(run_id, "loading", {"window": [run.window_start_lsn, run.window_end_lsn]})

        try:
            stream = db.get(ChangeStream, run.stream_id)
            if stream is None:
                raise RuntimeError(f"变更流不存在 stream_id={run.stream_id}")

            target = db.get(MergeTarget, run.target_id) if run.target_id else None
            strategy = target.strategy if target else MergeStrategy.UPSERT.value

            rows = (
                db.query(CdcEvent)
                .filter(
                    CdcEvent.stream_id == stream.id,
                    CdcEvent.lsn >= run.window_start_lsn,
                    CdcEvent.lsn <= run.window_end_lsn,
                )
                .order_by(CdcEvent.lsn.asc(), CdcEvent.received_seq.asc())
                .all()
            )
            event_index = {str(row.id): row for row in rows}
            payload = [
                {
                    "id": str(row.id),
                    "lsn": row.lsn,
                    "received_seq": row.received_seq,
                    "op": row.op,
                    "pk_value": row.pk_value,
                    "before_json": row.before_json,
                    "after_json": row.after_json,
                    "reject_reason": row.reject_reason,
                    "reject_detail": row.reject_detail,
                }
                for row in rows
            ]
            _progress(run_id, "merging", {"events": len(payload)})

            result = compute_merge(
                payload,
                pk_column=stream.pk_column,
                strategy=strategy,
                window_start=run.window_start_lsn,
                window_end=run.window_end_lsn,
            )
            _progress(run_id, "persisting", result["counts"])

            twin = (
                db.query(func.count(MergeRun.id))
                .filter(
                    MergeRun.stream_id == run.stream_id,
                    MergeRun.window_start_lsn == run.window_start_lsn,
                    MergeRun.window_end_lsn == run.window_end_lsn,
                    MergeRun.result_digest == result["digest"],
                    MergeRun.status == RunStatus.SUCCEEDED.value,
                    MergeRun.id != run.id,
                )
                .scalar()
                or 0
            )
            result["idempotent"] = bool(twin)
            result["executed_by"] = "worker"

            rejected_created = 0
            for item in result["rejected"]:
                exists = (
                    db.query(RejectedEvent)
                    .filter(
                        RejectedEvent.stream_id == stream.id,
                        RejectedEvent.lsn == item["lsn"],
                        RejectedEvent.reason == item["reason"],
                    )
                    .one_or_none()
                )
                if exists is not None:
                    if exists.run_id is None:
                        exists.run_id = run.id
                    continue
                source = event_index.get(str(item["event_id"]))
                db.add(
                    RejectedEvent(
                        event_id=item["event_id"] or None,
                        run_id=run.id,
                        stream_id=stream.id,
                        lsn=item["lsn"],
                        reason=item["reason"],
                        detail=item["detail"] or "",
                        payload_json={
                            "op": source.op if source else "update",
                            "pk_value": source.pk_value if source else item.get("pk"),
                            "before": source.before_json if source else None,
                            "after": source.after_json if source else None,
                        },
                        status=RejectStatus.PENDING.value,
                    )
                )
                rejected_created += 1

            counts = result["counts"]
            run.received_count = counts["received"]
            run.processed_count = counts["processed"]
            run.duplicate_count = counts["duplicate"]
            run.rejected_count = counts["rejected"]
            run.inserted_count = counts["inserted"]
            run.updated_count = counts["updated"]
            run.deleted_count = counts["deleted"]
            run.upserted_count = counts["upserted"]
            run.watermark_after = result["watermark_after"]
            run.result_digest = result["digest"]
            run.result_json = result
            run.duration_ms = max(1, int((time.perf_counter() - started) * 1000))
            run.status = RunStatus.SUCCEEDED.value
            run.finished_at = datetime.now(timezone.utc)

            # 只有窗口与水位线连续时才推进水位线；有空洞就停在水位线处
            if run.window_start_lsn <= int(stream.watermark_lsn) + 1:
                stream.watermark_lsn = max(int(stream.watermark_lsn), int(result["watermark_after"]))
            stream.status = "healthy" if int(stream.max_lsn) <= int(stream.watermark_lsn) else stream.status
            db.commit()

            _progress(run_id, "done", counts)
            logger.info(
                "merge done run=%s stream=%s processed=%s duplicate=%s rejected=%s upserted=%s idempotent=%s",
                run_id,
                stream.name,
                counts["processed"],
                counts["duplicate"],
                counts["rejected"],
                counts["upserted"],
                result["idempotent"],
            )
            return {
                "run_id": run_id,
                "status": run.status,
                "counts": counts,
                "idempotent": result["idempotent"],
                "rejected_created": rejected_created,
            }
        except Exception as exc:  # noqa: BLE001 - 任务失败必须落库
            db.rollback()
            run = db.get(MergeRun, run_id)
            if run is not None:
                run.status = RunStatus.FAILED.value
                run.error_message = str(exc)[:600]
                run.finished_at = datetime.now(timezone.utc)
                run.duration_ms = max(1, int((time.perf_counter() - started) * 1000))
                db.commit()
            _progress(run_id, "failed", {"error": str(exc)[:200]})
            logger.error("merge failed run=%s error=%s", run_id, exc, exc_info=True)
            return {"run_id": run_id, "status": "failed", "error": str(exc)}

