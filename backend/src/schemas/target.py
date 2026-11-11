from __future__ import annotations

from typing import Any


def serialize_target(target: Any) -> dict[str, Any]:
    from src.constants.enums import ENUM_LABELS
    from src.utils.formatters import iso

    return {
        "id": str(target.id),
        "name": target.name,
        "target_db": target.target_db,
        "target_table": target.target_table,
        "pk_column": target.pk_column,
        "strategy": target.strategy,
        "strategy_label": ENUM_LABELS["MergeStrategy"].get(target.strategy, target.strategy),
        "description": target.description,
        "created_at": iso(target.created_at),
    }
