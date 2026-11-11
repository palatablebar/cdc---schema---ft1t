"""worker 心跳：beat 每 20s 往 Redis 写时间戳，healthcheck 依赖它。"""
from __future__ import annotations

import time

import redis

from src.config.celery_app import celery_app
from src.config.settings import settings


@celery_app.task(name="cdcmerge.worker_heartbeat")
def worker_heartbeat() -> str:
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    client.set("cdcmerge:worker:heartbeat", str(time.time()), ex=180)
    return "ok"
