from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.controllers import meta_controller
from src.middlewares.auth import get_current_user
from src.models.user import User

router = APIRouter(tags=["meta"])


@router.get("/board")
def board(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return meta_controller.board(db)


@router.get("/meta/enums")
def enums(user: User = Depends(get_current_user)) -> dict:
    return meta_controller.enums()
