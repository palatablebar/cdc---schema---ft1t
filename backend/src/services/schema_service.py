"""schema 版本服务：按流列版本、调算法 2 做字段级 diff、生成迁移 SQL。"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from src.constants import error_codes as codes
from src.models.change_stream import ChangeStream
from src.models.schema_version import SchemaVersion
from src.schemas.schema_diff import serialize_schema_version
from src.services import schema_engine
from src.utils.errors import AppError, not_found


def list_versions(db: Session, stream_id: str) -> dict[str, Any]:
    rows = (
        db.query(SchemaVersion)
        .filter(SchemaVersion.stream_id == stream_id)
        .order_by(SchemaVersion.created_at.asc())
        .all()
    )
    return {"items": [serialize_schema_version(row) for row in rows], "total": len(rows)}


def get_version(db: Session, version_id: str) -> SchemaVersion:
    row = db.get(SchemaVersion, version_id)
    if row is None:
        raise AppError(codes.SCHEMA_VERSION_MISSING, "schema 版本不存在", f"version_id={version_id}")
    return row


def diff(db: Session, left_version_id: str, right_version_id: str) -> dict[str, Any]:
    if left_version_id == right_version_id:
        raise AppError(codes.SCHEMA_SAME_VERSION, "左右版本相同，无需比较", "same version id")

    left = get_version(db, left_version_id)
    right = get_version(db, right_version_id)
    if str(left.stream_id) != str(right.stream_id):
        raise AppError(
            codes.VALIDATION_ERROR,
            "两个版本不属于同一条变更流",
            f"left.stream={left.stream_id} right.stream={right.stream_id}",
        )

    stream = db.get(ChangeStream, left.stream_id)
    if stream is None:
        raise not_found("ChangeStream", left.stream_id)

    left_payload = {
        "version_label": left.version_label,
        "fields": left.fields_json or [],
        "pk_columns": [f["name"] for f in (left.fields_json or []) if f.get("is_pk")] or [stream.pk_column],
    }
    right_payload = {
        "version_label": right.version_label,
        "fields": right.fields_json or [],
        "pk_columns": [f["name"] for f in (right.fields_json or []) if f.get("is_pk")] or [stream.pk_column],
    }

    target_table = f"dw.{stream.name}_dw"
    result = schema_engine.diff_schemas(left_payload, right_payload, target_table)
    result["left_version"] = serialize_schema_version(left)
    result["right_version"] = serialize_schema_version(right)
    result["stream"] = {
        "id": str(stream.id),
        "name": stream.name,
        "source_table": stream.source_table,
    }
    result["target_table"] = target_table
    return result


def version_compare_pairs(db: Session, stream_id: str) -> list[dict[str, str]]:
    """默认比较对：相邻两个版本（给前端做默认选中）。"""
    rows = (
        db.query(SchemaVersion)
        .filter(SchemaVersion.stream_id == stream_id)
        .order_by(SchemaVersion.created_at.asc())
        .all()
    )
    pairs = []
    for index in range(1, len(rows)):
        pairs.append(
            {
                "left_version_id": str(rows[index - 1].id),
                "right_version_id": str(rows[index].id),
                "label": f"{rows[index - 1].version_label} → {rows[index].version_label}",
            }
        )
    return pairs
