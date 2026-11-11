"""通用 schema 基类与分页结构。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")


class ErrorOut(BaseModel):
    code: str
    message: str
    detail: str = ""
    trace_id: str | None = None
    extra: dict[str, Any] = {}


class PageOut(BaseModel):
    items: list[dict[str, Any]]
    total: int
    offset: int
    limit: int


class OkOut(BaseModel):
    ok: bool = True
    message: str = ""
