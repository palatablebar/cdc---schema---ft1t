"""窗口归并结果发布到数仓目标表（真实物理写入，整窗原子）。

发布分两步，先过 schema gate 再写库，任一步失败都保证目标表不留半批数据：

1. schema gate（纯函数，无 IO）：把窗口内**每一条真正参与归并的事件**与目标表
   实际列做逐字段兼容性检查。任一字段不兼容即判定整窗 BLOCKED，列出全部阻塞
   字段（event/lsn/pk/field/原因），随后不执行任何写入。
2. 事务发布：所有 upsert / delete 在同一个数据库事务内完成，配合
   `_merge_lsn` 位点列做 LSN 守卫——只允许更新位点的事件覆盖旧值，重复投递和
   迟到的旧事件即使被再次执行也不会回写当前值；事务失败整体回滚。

同一窗口重跑：upsert 的 WHERE 守卫让旧 LSN 全部 no-op，目标表内容与 digest
保持不变，得到唯一结果。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.models.merge_target import MergeTarget
from src.models.schema_version import SchemaVersion
from src.services.schema_engine import family_of, parse_type
from src.utils.logger import get_logger

logger = get_logger("cdcmerge.publish")

# 归并写入的位点列：记录目标行最后一次被哪个 LSN 的事件更新
MERGE_LSN_COLUMN = "_merge_lsn"
# 目标表内容快照最多带回多少行（运行详情用，防止 JSONB 无限膨胀）
SNAPSHOT_LIMIT = 500

# gate 阻塞原因（英文枚举，前端有中文映射）
REASON_UNKNOWN_COLUMN = "unknown_column"
REASON_TYPE_INCOMPATIBLE = "type_incompatible"
REASON_REQUIRED_MISSING = "required_missing"
REASON_NULLABLE = "not_null_violation"


@dataclass
class BlockingItem:
    event_id: str
    lsn: int
    pk: str | None
    field: str
    reason: str
    detail: str
    expected_type: str | None = None
    actual_type: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "lsn": self.lsn,
            "pk": self.pk,
            "field": self.field,
            "reason": self.reason,
            "reason_label": BLOCKING_REASON_LABELS.get(self.reason, self.reason),
            "detail": self.detail,
            "expected_type": self.expected_type,
            "actual_type": self.actual_type,
        }


BLOCKING_REASON_LABELS = {
    REASON_UNKNOWN_COLUMN: "目标表不存在该列",
    REASON_TYPE_INCOMPATIBLE: "字段类型不兼容",
    REASON_REQUIRED_MISSING: "必填字段缺失",
    REASON_NULLABLE: "非空列收到 NULL",
}


@dataclass
class TargetSnapshot:
    target_table: str
    row_count: int
    truncated: bool
    columns: list[str]
    rows: list[dict[str, Any]] = field(default_factory=list)


# ------------------------------------------------------------------ 工具 ----


def split_table_name(target_table: str) -> tuple[str, str]:
    """`dw.orders_dw` -> ("dw", "orders_dw")；缺 schema 时补 settings.target_schema。"""
    if "." in target_table:
        schema, table = target_table.split(".", 1)
    else:
        schema, table = settings.target_schema, target_table
    return schema.strip(), table.strip()


def quote_ident(name: str) -> str:
    """PostgreSQL 双引号转义，防止目标表名/列名注入。"""
    return '"' + str(name).replace('"', '""') + '"'


def qualified_name(schema: str, table: str) -> str:
    return f"{quote_ident(schema)}.{quote_ident(table)}"


def inspect_target_columns(db: Session, target: MergeTarget) -> list[dict[str, Any]] | None:
    """读目标表实际物理列（information_schema），表不存在返回 None。"""
    schema, table = split_table_name(target.target_table)
    rows = db.execute(
        text(
            """
            SELECT column_name, data_type, is_nullable, column_default,
                   character_maximum_length, numeric_precision, numeric_scale
              FROM information_schema.columns
             WHERE table_schema = :schema AND table_name = :table
             ORDER BY ordinal_position
            """
        ),
        {"schema": schema, "table": table},
    ).mappings().all()
    if not rows:
        return None
    columns = []
    for row in rows:
        base, params = parse_type(row["data_type"])
        columns.append(
            {
                "name": row["column_name"],
                "type": row["data_type"],
                "base_type": base,
                "type_params": params,
                "nullable": row["is_nullable"] == "YES",
                "default": row["column_default"],
                "length": row["character_maximum_length"],
            }
        )
    return columns


def latest_schema_fields(db: Session, stream_id: Any) -> dict[str, dict[str, Any]]:
    """取该流最新 SchemaVersion 的字段定义，作为类型口径的补充参考。"""
    version = (
        db.query(SchemaVersion)
        .filter(SchemaVersion.stream_id == stream_id)
        .order_by(SchemaVersion.created_at.desc(), SchemaVersion.version_label.desc())
        .first()
    )
    if version is None:
        return {}
    return {str(item["name"]): dict(item) for item in (version.fields_json or [])}


# ------------------------------------------------------------------ gate ----


def _value_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "text"
    if isinstance(value, (dict, list)):
        return "json"
    return type(value).__name__


def _value_compatible(value: Any, column: dict[str, Any]) -> bool:
    """判定单个 Python 值能否安全写入该物理列（按 PostgreSQL 隐式转换口径，收紧到可预期集合）。"""
    if value is None:
        return column["nullable"]

    family = family_of(column["base_type"])
    if isinstance(value, bool):
        return family == "boolean"
    if isinstance(value, int):
        # integer/numeric/float 都能容纳整数；boolean/text 不行
        return family in {"integer", "numeric", "float"}
    if isinstance(value, float):
        return family in {"numeric", "float"}
    if isinstance(value, str):
        if family == "text":
            length = column.get("length")
            return length is None or len(value) <= int(length)
        if family == "temporal":
            # 时间戳/日期列只接受 ISO 文本或 Python 时间对象，普通业务字符串不兼容
            return _looks_like_iso_temporal(value)
        return False
    if isinstance(value, (dict, list)):
        return family == "json"
    return False


def _looks_like_iso_temporal(value: str) -> bool:
    text_value = value.strip()
    if len(text_value) < 8:
        return False
    head = text_value[:4]
    return head.isdigit() and text_value[4:5] in ("-",)


def check_window_compatibility(
    applied_events: list[dict[str, Any]],
    target_columns: list[dict[str, Any]],
    schema_fields: dict[str, dict[str, Any]],
    pk_column: str,
) -> list[BlockingItem]:
    """整窗 schema gate：逐条事件 × 逐字段检查，返回全部阻塞项（空列表 = 可发布）。"""
    columns = {col["name"]: col for col in target_columns}
    blocking: list[BlockingItem] = []

    for event in applied_events:
        event_id = event["event_id"]
        lsn = int(event["lsn"])
        pk = event.get("pk")
        op = event.get("op")
        after = event.get("after") or {}

        # delete 不携带行值，只要主键列仍在目标表里即可
        if op == "delete":
            if pk_column not in columns:
                blocking.append(
                    BlockingItem(event_id, lsn, pk, pk_column, REASON_UNKNOWN_COLUMN,
                                 f"目标表缺少主键列 {pk_column}，无法定位删除行")
                )
            continue

        for field_name, value in after.items():
            column = columns.get(field_name)
            if column is None:
                blocking.append(
                    BlockingItem(
                        event_id, lsn, pk, field_name, REASON_UNKNOWN_COLUMN,
                        f"事件字段 {field_name} 在目标表中不存在（当前目标版本未包含该列）",
                        expected_type=None,
                        actual_type=_value_type_name(value),
                    )
                )
                continue

            if value is None and not column["nullable"]:
                blocking.append(
                    BlockingItem(
                        event_id, lsn, pk, field_name, REASON_NULLABLE,
                        f"非空列 {field_name} 收到 NULL",
                        expected_type=column["type"], actual_type="null",
                    )
                )
                continue

            if not _value_compatible(value, column):
                schema_field = schema_fields.get(field_name)
                expected = column["type"]
                if schema_field and schema_field.get("type"):
                    expected = f"{expected}（schema 版本口径 {schema_field['type']}）"
                blocking.append(
                    BlockingItem(
                        event_id, lsn, pk, field_name, REASON_TYPE_INCOMPATIBLE,
                        f"字段 {field_name} 期望 {column['type']}，实际收到 {_value_type_name(value)}: {_preview(value)}",
                        expected_type=expected,
                        actual_type=_value_type_name(value),
                    )
                )

        # 目标表必填列（无默认值、不可空）在 insert 载荷里缺失 → 整窗阻塞
        if op == "insert":
            for field_name, column in columns.items():
                if field_name == MERGE_LSN_COLUMN:
                    continue
                if column["nullable"] or column.get("default") is not None:
                    continue
                if field_name not in after:
                    blocking.append(
                        BlockingItem(
                            event_id, lsn, pk, field_name, REASON_REQUIRED_MISSING,
                            f"必填字段 {field_name} 在 insert 事件中缺失且目标列无默认值",
                            expected_type=column["type"], actual_type=None,
                        )
                    )

    # 同一 (event, field, reason) 去重，避免重复投递刷出重复阻塞项
    seen: set[tuple[str, str, str]] = set()
    deduped: list[BlockingItem] = []
    for item in blocking:
        key = (item.event_id, item.field, item.reason)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    deduped.sort(key=lambda item: (item.lsn, item.field, item.reason))
    return deduped


def _preview(value: Any, limit: int = 40) -> str:
    text_value = repr(value)
    return text_value if len(text_value) <= limit else text_value[:limit] + "…"


# ------------------------------------------------------------- 发布 / 快照 ----


def _coerce_for_json(value: Any) -> Any:
    """Decimal/datetime 等不能直接进 JSONB 的值转成可序列化形态。"""
    from decimal import Decimal
    from datetime import date, datetime

    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def fetch_target_snapshot(db: Session, target: MergeTarget) -> TargetSnapshot:
    schema, table = split_table_name(target.target_table)
    name = qualified_name(schema, table)
    total = db.execute(text(f"SELECT count(*) FROM {name}")).scalar() or 0
    columns_rows = db.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_schema = :schema AND table_name = :table
             ORDER BY ordinal_position
            """
        ),
        {"schema": schema, "table": table},
    ).all()
    columns = [row[0] for row in columns_rows]
    truncated = total > SNAPSHOT_LIMIT
    rows = db.execute(
        text(f"SELECT * FROM {name} ORDER BY 1 ASC LIMIT :limit"),
        {"limit": SNAPSHOT_LIMIT},
    ).mappings().all()
    return TargetSnapshot(
        target_table=target.target_table,
        row_count=int(total),
        truncated=truncated,
        columns=columns,
        rows=[{key: _coerce_for_json(value) for key, value in dict(row).items()} for row in rows],
    )


def publish_window(
    db: Session,
    target: MergeTarget,
    stream_id: Any,
    merge_result: dict[str, Any],
) -> dict[str, Any]:
    """把一次窗口归并结果原子发布到目标表，返回发布详情（同时写入 result_json.publish）。

    流程：
      gate 不通过 -> 不触碰目标表，返回 published=False + blocking_fields；
      gate 通过   -> 单事务执行带 LSN 守卫的 upsert/delete，再回读真实内容与行数。
    """
    target_columns = inspect_target_columns(db, target)
    if target_columns is None:
        return {
            "published": False,
            "reason": "target_missing",
            "detail": f"目标表 {target.target_table} 不存在，无法发布",
            "blocking_fields": [],
        }

    applied_events = merge_result.get("applied_events") or []
    blocking = check_window_compatibility(
        applied_events,
        target_columns,
        latest_schema_fields(db, stream_id),
        target.pk_column,
    )
    if blocking:
        logger.warning(
            "publish blocked target=%s blocking=%d",
            target.target_table,
            len(blocking),
        )
        return {
            "published": False,
            "reason": "schema_gate",
            "detail": f"{len(blocking)} 个字段与目标表版本不兼容，整窗不发布",
            "blocking_fields": [item.as_dict() for item in blocking],
            "target_table": target.target_table,
        }

    schema, table = split_table_name(target.target_table)
    name = qualified_name(schema, table)
    before = fetch_target_snapshot(db, target)

    physical_columns = {col["name"] for col in target_columns}
    data_columns = [col for col in physical_columns if col != MERGE_LSN_COLUMN]
    pk_column = target.pk_column

    upserted = stale_skipped = deleted = delete_skipped = 0

    try:
        # 1) 最终行：带 LSN 守卫的 upsert。迟到旧事件/重复投递的位点不大于当前值时整行 no-op。
        for row in merge_result.get("rows", []):
            values = dict(row.get("values") or {})
            lsn = int(row["last_lsn"])
            payload = {
                key: _coerce_for_json(value)
                for key, value in values.items()
                if key in data_columns and key != MERGE_LSN_COLUMN
            }
            if pk_column not in payload:
                payload[pk_column] = row["pk"]

            col_names = list(payload.keys())
            params = {f"p_{index}": value for index, value in enumerate(payload.values())}
            params["p_lsn"] = lsn
            column_sql = ", ".join(quote_ident(col) for col in col_names + [MERGE_LSN_COLUMN])
            value_sql = ", ".join(f":p_{index}" for index in range(len(col_names))) + ", :p_lsn"
            # 至少要更新位点列；业务列可能为空（载荷只含主键的极端情况）
            set_parts = [
                f"{quote_ident(col)} = EXCLUDED.{quote_ident(col)}"
                for col in col_names
                if col not in (pk_column, MERGE_LSN_COLUMN)
            ]
            set_parts.append(f"{quote_ident(MERGE_LSN_COLUMN)} = EXCLUDED.{quote_ident(MERGE_LSN_COLUMN)}")
            update_sql = ", ".join(set_parts)
            guard = f"{name}.{quote_ident(MERGE_LSN_COLUMN)} IS NULL OR {name}.{quote_ident(MERGE_LSN_COLUMN)} < :p_lsn"
            sql = (
                f"INSERT INTO {name} ({column_sql}) VALUES ({value_sql}) "
                f"ON CONFLICT ({quote_ident(pk_column)}) DO UPDATE SET "
                f"{update_sql} "
                f"WHERE {guard} "
                f"RETURNING (xmax = 0) AS inserted"
            )
            outcome = db.execute(text(sql), params)
            returned = outcome.fetchone()
            if returned is None:
                stale_skipped += 1
            else:
                upserted += 1

        # 2) 本窗 tombstone：同样带位点守卫，旧于当前行位点的删除不生效。
        for tomb in merge_result.get("tombstones", []):
            outcome = db.execute(
                text(
                    f"DELETE FROM {name} "
                    f"WHERE {quote_ident(pk_column)} = :pk "
                    f"AND ({quote_ident(MERGE_LSN_COLUMN)} IS NULL OR {quote_ident(MERGE_LSN_COLUMN)} <= :lsn)"
                ),
                {"pk": tomb["pk"], "lsn": int(tomb["last_lsn"])},
            )
            if outcome.rowcount and outcome.rowcount > 0:
                deleted += 1
            else:
                delete_skipped += 1

        after = fetch_target_snapshot(db, target)
    except Exception as exc:  # noqa: BLE001 - 发布失败必须回滚，由上层把 run 落为 failed
        db.rollback()
        logger.error("publish failed target=%s error=%s", target.target_table, exc, exc_info=True)
        raise

    return {
        "published": True,
        "reason": None,
        "detail": "整窗 schema gate 通过，已在单事务内发布到目标表",
        "blocking_fields": [],
        "target_table": target.target_table,
        "guarded_upserts": upserted,
        "stale_upserts_skipped": stale_skipped,
        "guarded_deletes": deleted,
        "stale_deletes_skipped": delete_skipped,
        "row_count_before": before.row_count,
        "row_count_after": after.row_count,
        "target_columns": after.columns,
        "target_snapshot_truncated": after.truncated,
        "target_rows": after.rows,
    }
