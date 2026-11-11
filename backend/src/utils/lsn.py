"""LSN 区间与展示工具（后端唯一实现，前端只做格式化）。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LsnWindow:
    start: int
    end: int

    @property
    def size(self) -> int:
        return max(0, self.end - self.start + 1)

    def contains(self, lsn: int) -> bool:
        return self.start <= lsn <= self.end

    def as_dict(self) -> dict[str, int]:
        return {"start": self.start, "end": self.end, "size": self.size}


def normalize_window(start: int | None, end: int | None, watermark: int, max_lsn: int) -> LsnWindow:
    """缺省窗口 = 水位线之后到最新 LSN。"""
    resolved_start = watermark + 1 if start is None else start
    resolved_end = max_lsn if end is None else end
    return LsnWindow(start=resolved_start, end=resolved_end)


def first_gap(seen: set[int], window: LsnWindow) -> int | None:
    """窗口内最小的未到达 LSN；无空洞返回 None。"""
    for lsn in range(window.start, window.end + 1):
        if lsn not in seen:
            return lsn
    return None
