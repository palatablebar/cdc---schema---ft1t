"""接口输出格式化：枚举中文名、时间、LSN 展示。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from src.constants.enums import ENUM_LABELS


def enum_label(enum_name: str, value: str | None) -> str:
    if value is None:
        return ""
    return ENUM_LABELS.get(enum_name, {}).get(value, value)


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def format_lsn(lsn: int | None) -> str:
    """LSN 展示成 12 位定宽数字，前端表格不抖。"""
    if lsn is None:
        return "-"
    return f"{lsn:012d}"


def json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value
