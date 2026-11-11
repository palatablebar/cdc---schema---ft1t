from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.limits import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from src.controllers import stream_controller
from src.middlewares.rbac import require_permission
from src.models.user import User
from src.schemas.event import EventQuery
from src.schemas.stream import StreamCreateRequest, StreamUpdateRequest

router = APIRouter(prefix="/streams", tags=["stream"])


@router.get("")
def list_streams(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("streams:read")),
) -> dict:
    return stream_controller.list_streams(db)


@router.post("")
def create_stream(
    request: Request,
    payload: StreamCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("streams:write")),
) -> dict:
    return stream_controller.create_stream(request, payload, user, db)


@router.get("/{stream_id}")
def get_stream(
    stream_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("streams:read")),
) -> dict:
    return stream_controller.get_stream(stream_id, db)


@router.patch("/{stream_id}")
def update_stream(
    request: Request,
    stream_id: str,
    payload: StreamUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("streams:write")),
) -> dict:
    return stream_controller.update_stream(request, stream_id, payload, user, db)


@router.get("/{stream_id}/events")
def list_events(
    stream_id: str,
    op: str | None = None,
    pk: str | None = None,
    only_rejected: bool = False,
    order: str = "lsn",
    offset: int = 0,
    limit: int = DEFAULT_PAGE_SIZE,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("events:read")),
) -> dict:
    query = EventQuery(
        op=op,
        pk=pk,
        only_rejected=only_rejected,
        order=order,
        offset=offset,
        limit=min(limit, MAX_PAGE_SIZE),
    )
    return stream_controller.list_events(stream_id, query, db)


@router.get("/{stream_id}/arrival-stats")
def arrival_stats(
    stream_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("events:read")),
) -> dict:
    return stream_controller.arrival_stats(stream_id, db)
