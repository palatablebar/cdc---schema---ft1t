from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.controllers import meta_controller
from src.middlewares.rbac import require_permission
from src.models.user import User

router = APIRouter(tags=["audit"])


@router.get("/audit")
def audit_logs(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit:read")),
) -> dict:
    return meta_controller.audit_logs(db, min(limit, 200), offset)
