from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.config.settings import settings
from src.models.base import Base, TimestampMixin, new_uuid, utcnow


class ChangeStream(Base, TimestampMixin):
    """一条 CDC 变更流：源库源表 + 主键 + 当前水位线。"""

    __tablename__ = "change_streams"
    __table_args__ = {"schema": settings.cdc_schema}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    source_db: Mapped[str] = mapped_column(String(120), nullable=False)
    source_table: Mapped[str] = mapped_column(String(160), nullable=False)
    pk_column: Mapped[str] = mapped_column(String(80), nullable=False, default="id")
    watermark_lsn: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    max_lsn: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="healthy", index=True)
    description: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    owner_team: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
