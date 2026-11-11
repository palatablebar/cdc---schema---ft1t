"""运行进度写 Redis，供前端轮询时展示更细的相位（不落库，避免污染业务表）。"""
from __future__ import annotations

import json
from typing import Any

from src.utils.redis_client import get_redis


def publish(run_id: str, phase: str, detail: dict[str, Any] | None = None) -> None:
    try:
        get_redis().setex(
            f"cdcmerge:progress:{run_id}",
            3600,
            json.dumps({"phase": phase, "detail": detail or {}}, ensure_ascii=False),
        )
    except Exception:  # noqa: BLE001 - 进度不是关键路径
        pass


def read(run_id: str) -> dict[str, Any] | None:
    try:
        raw = get_redis().get(f"cdcmerge:progress:{run_id}")
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001
        return None
