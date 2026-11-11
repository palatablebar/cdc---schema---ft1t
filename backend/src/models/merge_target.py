from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.config.settings import settings
from src.models.base import Base, TimestampMixin, new_uuid, utcnow


class MergeTarget(Base, TimestampMixin):
    """归并目标表：目标库表 + 主键 + 策略（upsert / append）。"""

    __tablename__ = "merge_targets"
    __table_args__ = {"schema": settings.cdc_schema}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    target_db: Mapped[str] = mapped_column(String(120), nullable=False, default="dw")
    target_table: Mapped[str] = mapped_column(String(200), nullable=False)
    pk_column: Mapped[str] = mapped_column(String(80), nullable=False, default="id")
    strategy: Mapped[str] = mapped_column(String(20), nullable=False, default="upsert")
    description: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
