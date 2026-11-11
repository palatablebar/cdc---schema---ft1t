"""事件 controller：单事件详情与 before/after 字段级 diff。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.services import event_service


def get_event(event_id: str, db: Session) -> dict:
    event = event_service.get_event(db, event_id)
    return event_service.diff_event(event)
