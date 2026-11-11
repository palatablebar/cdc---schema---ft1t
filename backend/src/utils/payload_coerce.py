"""拒绝事件重放时的载荷修复：解析失败 / schema 不匹配 / 类型冲突。

这些规则是「重放」这个动作的真实业务逻辑，不是占位实现：
- parse_error：去掉千分位与货币符号后按目标类型重解析；
- schema_mismatch：用最新 SchemaVersion 的字段定义补默认值；
- type_conflict：按目标类型强制转换，失败则放弃；
- pk_missing：无法自动修复（主键是业务事实，不能猜）。
"""
from __future__ import annotations

import re
from typing import Any

from src.constants.enums import RejectReason

_NUMERIC_NOISE = re.compile(r"[¥$,\s]")

NUMERIC_TYPES = ("numeric", "decimal", "integer", "bigint", "int", "smallint", "double", "real")
INTEGER_TYPES = ("integer", "bigint", "int", "smallint")


def strip_numeric_noise(raw: str) -> str:
    return _NUMERIC_NOISE.sub("", raw)


def coerce_scalar(value: Any, sql_type: str) -> tuple[Any, str | None]:
    """返回 (转换后的值, 错误说明)。sql_type 取基础类型名。"""
    base = sql_type.split("(")[0].strip().lower()
    if value is None:
        return None, None
    if base in NUMERIC_TYPES:
        if isinstance(value, (int, float)):
            return value, None
        text = strip_numeric_noise(str(value))
        try:
            if base in INTEGER_TYPES:
                return int(float(text)), None
            return float(text), None
        except ValueError:
            return None, f"无法把 {value!r} 解析为 {sql_type}"
    if base in ("text", "varchar", "char", "string"):
        return str(value), None
    if base == "boolean":
        lowered = str(value).strip().lower()
        if lowered in ("1", "true", "t", "yes"):
            return True, None
        if lowered in ("0", "false", "f", "no"):
            return False, None
        return None, f"无法把 {value!r} 解析为 boolean"
    return value, None


def repair_payload(
    reason: str,
    payload: dict[str, Any] | None,
    fields: list[dict[str, Any]],
    pk_column: str,
) -> tuple[dict[str, Any] | None, str]:
    """返回 (修复后的载荷 or None, 说明)。"""
    if reason == RejectReason.PK_MISSING.value:
        return None, "主键缺失属于业务事实缺失，不能自动重放"
    if not payload:
        return None, "原始载荷为空，无法重放"

    repaired = dict(payload)
    notes: list[str] = []

    for field in fields:
        name = field["name"]
        sql_type = field.get("type", "text")
        if name in repaired and repaired[name] is not None:
            coerced, error = coerce_scalar(repaired[name], sql_type)
            if error:
                return None, error
            if coerced is not None and coerced != repaired[name]:
                notes.append(f"{name}: {repaired[name]!r}→{coerced!r}")
            repaired[name] = coerced
            continue

        # 缺字段：有默认值用它；可空补 None；必填无默认值 → 修复失败
        if field.get("default") is not None:
            repaired[name] = field["default"]
            notes.append(f"{name}: 补默认值 {field['default']!r}")
        elif field.get("nullable", True):
            repaired[name] = None
            notes.append(f"{name}: 补 null")
        else:
            return None, f"必填字段 {name} 缺失且无默认值"

    pk_value = repaired.get(pk_column)
    if pk_value in (None, ""):
        return None, f"主键 {pk_column} 缺失"

    summary = "；".join(notes) if notes else "载荷已符合当前 schema"
    return repaired, summary
