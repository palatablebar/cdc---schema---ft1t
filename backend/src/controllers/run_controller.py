"""归并运行 controller。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.models.user import User
from src.schemas.run import RunCreateRequest
from src.services import audit_service, run_service


def create_run(request: Request, payload: RunCreateRequest, user: User, db: Session) -> dict:
    run = run_service.create_run(
        db,
        payload.stream_id,
        payload.window_start_lsn,
        payload.window_end_lsn,
        str(user.id),
    )
    audit_service.record(
        db,
        action="run.trigger",
        entity_type="MergeRun",
        entity_id=str(run.id),
        actor_id=str(user.id),
        payload={
            "stream_id": payload.stream_id,
            "window": [run.window_start_lsn, run.window_end_lsn],
            "status": run.status,
        },
        ip=getattr(request.state, "client_ip", None),
        trace_id=getattr(request.state, "trace_id", None),
    )
    return run_service.run_detail(db, str(run.id))


def list_runs(stream_id: str | None, limit: int, db: Session) -> dict:
    return run_service.list_runs(db, stream_id=stream_id, limit=limit)


def get_run(run_id: str, db: Session) -> dict:
    return run_service.run_detail(db, run_id)
