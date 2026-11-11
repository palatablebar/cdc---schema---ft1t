from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.config.settings import settings
from src.models.base import Base, utcnow


class MergeRun(Base):
    """一次归并运行：窗口 + 计数 + 结果 JSON + 幂等摘要。"""

    __tablename__ = "merge_runs"
    __table_args__ = {"schema": settings.cdc_schema}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stream_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    window_start_lsn: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    window_end_lsn: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    received_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    upserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    watermark_before: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    watermark_after: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_digest: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # 数仓发布状态：True=已写入目标表；False=gate 阻塞/未发布；None=尚未进入发布阶段
    published: Mapped[bool | None] = mapped_column(nullable=True, index=True)
    # 发布详情（阻塞字段、入库前后行数、目标表快照、LSN 守卫跳过数），结构见 target_publisher
    publish_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    target_rows_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_rows_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(600), nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
