"""Celery 入口（backend 侧只投递任务，真正消费在 worker 容器）。"""
from __future__ import annotations

from celery import Celery

from src.config.settings import settings

celery_app = Celery(
    "cdcmerge",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.tasks_dispatcher"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_track_started=True,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
)

# 任务名 -> worker 侧真实实现（共享任务名，跨容器解耦）
TASK_MERGE_RUN = "cdcmerge.merge_run"
TASK_REPLAY_EVENT = "cdcmerge.replay_event"
