"""worker 复用 backend 的 settings（同一份环境变量、同一份默认值）。"""
from __future__ import annotations

from src.config.settings import settings  # noqa: F401 - 复用 backend 配置

__all__ = ["settings"]
