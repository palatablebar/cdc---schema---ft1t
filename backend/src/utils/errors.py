"""统一业务异常。"""
from __future__ import annotations

from typing import Any

from src.constants import error_codes as codes


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str | None = None,
        detail: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message or codes.ERROR_MESSAGES.get(code, code)
        self.detail = detail or ""
        self.extra = extra or {}
        super().__init__(self.message)

    @property
    def http_status(self) -> int:
        return codes.HTTP_STATUS.get(self.code, 500)

    def to_payload(self, trace_id: str | None = None) -> dict[str, Any]:
        payload = {
            "code": self.code,
            "message": self.message,
            "detail": self.detail,
            "trace_id": trace_id,
        }
        if self.extra:
            payload["extra"] = self.extra
        return payload


def not_found(entity: str, entity_id: object) -> AppError:
    return AppError(codes.NOT_FOUND, f"{entity} 不存在", f"{entity}[id={entity_id}] not found")
