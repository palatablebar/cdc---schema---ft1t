"""backend 侧任务投递封装；真正的 task 实现在 worker/src/tasks 下同名注册。"""
from __future__ import annotations

from src.config.celery_app import TASK_MERGE_RUN, celery_app
from src.utils.logger import get_logger

logger = get_logger("cdcmerge.dispatch")


def enqueue_merge_run(run_id: str) -> str | None:
    """投递合并任务；Broker 不可用时返回 None，由 service 决定降级。"""
    try:
        result = celery_app.send_task(TASK_MERGE_RUN, args=[run_id])
        logger.info("enqueued merge run_id=%s task_id=%s", run_id, result.id)
        return result.id
    except Exception as exc:  # noqa: BLE001
        logger.warning("enqueue merge failed run_id=%s error=%s", run_id, exc)
        return None
