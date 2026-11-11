from __future__ import annotations

from pydantic import BaseModel, Field


class EventQuery(BaseModel):
    op: str | None = None
    pk: str | None = None
    only_rejected: bool = False
    order: str = "lsn"
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)
