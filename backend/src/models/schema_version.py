from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.config.settings import settings
from src.models.base import Base, utcnow


class SchemaVersion(Base):
    """上游表的一个 DDL 版本快照。fields_json 是算法 2 的唯一输入。"""

    __tablename__ = "schema_versions"
    __table_args__ = {"schema": settings.cdc_schema}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stream_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    version_label: Mapped[str] = mapped_column(String(40), nullable=False)
    fields_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    ddl_summary: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
