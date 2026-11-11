from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.config.settings import settings
from src.models.base import Base, utcnow


class CdcEvent(Base):
    """一条 binlog 事件。received_seq 表示到达顺序，故意与 lsn 顺序不一致。"""

    __tablename__ = "cdc_events"
    __table_args__ = {"schema": settings.cdc_schema}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stream_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    lsn: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    received_seq: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    op: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    pk_value: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    reject_detail: Mapped[str | None] = mapped_column(String(400), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    replayed_from_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
