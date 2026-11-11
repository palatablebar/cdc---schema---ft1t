from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.controllers import event_controller
from src.middlewares.rbac import require_permission
from src.models.user import User

router = APIRouter(prefix="/events", tags=["event"])


@router.get("/{event_id}")
def get_event(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("events:read")),
) -> dict:
    return event_controller.get_event(event_id, db)
