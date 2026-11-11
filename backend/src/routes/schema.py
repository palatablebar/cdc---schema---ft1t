from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.controllers import schema_controller
from src.middlewares.rbac import require_permission
from src.models.user import User
from src.schemas.schema_diff import SchemaDiffRequest

router = APIRouter(tags=["schema"])


@router.get("/streams/{stream_id}/schema-versions")
def list_versions(
    stream_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("schema:read")),
) -> dict:
    return schema_controller.list_versions(stream_id, db)


@router.post("/schema/diff")
def diff_versions(
    request: Request,
    payload: SchemaDiffRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("schema:read")),
) -> dict:
    return schema_controller.diff_versions(request, payload, user, db)
