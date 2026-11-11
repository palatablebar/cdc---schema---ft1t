from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.controllers import rejected_controller
from src.middlewares.rbac import require_permission
from src.models.user import User

router = APIRouter(prefix="/rejected", tags=["rejected"])


@router.get("")
def list_rejected(
    stream_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("rejected:read")),
) -> dict:
    return rejected_controller.list_rejected(stream_id, status, min(limit, 200), offset, db)


@router.post("/{rejected_id}/replay")
def replay(
    request: Request,
    rejected_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("rejected:replay")),
) -> dict:
    return rejected_controller.replay(request, rejected_id, user, db)


@router.post("/{rejected_id}/dismiss")
def dismiss(
    request: Request,
    rejected_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("rejected:replay")),
) -> dict:
    return rejected_controller.dismiss(request, rejected_id, user, db)
