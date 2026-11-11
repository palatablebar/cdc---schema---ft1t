from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.controllers import run_controller
from src.middlewares.auth import get_current_user
from src.middlewares.rate_limit import rate_limit
from src.middlewares.rbac import require_permission
from src.models.user import User
from src.schemas.run import RunCreateRequest

router = APIRouter(prefix="/runs", tags=["run"])


@router.get("")
def list_runs(
    stream_id: str | None = None,
    limit: int = 30,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("runs:read")),
) -> dict:
    return run_controller.list_runs(stream_id, min(limit, 200), db)


@router.post("")
def create_run(
    request: Request,
    payload: RunCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("runs:trigger")),
    _rate: None = rate_limit("runs"),
) -> dict:
    return run_controller.create_run(request, payload, user, db)


@router.get("/{run_id}")
def get_run(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("runs:read")),
) -> dict:
    return run_controller.get_run(run_id, db)
