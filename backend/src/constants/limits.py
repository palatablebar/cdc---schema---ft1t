"""限额常量：单窗口事件、分页、限流桶。"""
from __future__ import annotations

from src.config.settings import settings

MAX_WINDOW_EVENTS = settings.max_window_events
MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50
RATE_LIMIT_RUNS_PER_MINUTE = settings.rate_limit_runs_per_minute
RATE_LIMIT_DEFAULT_PER_MINUTE = settings.rate_limit_default_per_minute
MAX_EVENTS_PER_PAGE = 120
