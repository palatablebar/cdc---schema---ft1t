"""worker 侧 Celery 应用：注册真实任务实现。"""
from __future__ import annotations

from celery import Celery

from src.config.settings import settings

celery_app = Celery("cdcmerge-worker", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_track_started=True,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)

celery_app.autodiscover_tasks(["worker_src.tasks"], force=True)

import worker_src.tasks.heartbeat_task  # noqa: E402,F401 - 注册 beat 任务
import worker_src.tasks.merge_task  # noqa: E402,F401 - 注册归并任务

celery_app.conf.beat_schedule = {
    "worker-heartbeat": {
        "task": "cdcmerge.worker_heartbeat",
        "schedule": 20.0,
    }
}
