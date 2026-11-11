from __future__ import annotations

from pydantic import BaseModel


class SchemaDiffRequest(BaseModel):
    left_version_id: str
    right_version_id: str


def serialize_schema_version(version: Any) -> dict:
    from src.utils.formatters import iso

    return {
        "id": str(version.id),
        "stream_id": str(version.stream_id),
        "version_label": version.version_label,
        "fields": version.fields_json,
        "field_count": len(version.fields_json or []),
        "ddl_summary": version.ddl_summary,
        "created_by": version.created_by,
        "created_at": iso(version.created_at),
    }
