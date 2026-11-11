"""事件服务：带过滤的分页查询 + 单事件 before/after 字段级 diff。

字段级 diff 也放在后端算，前端只渲染结果（前端 utils 只做格式化）。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.cdc_event import CdcEvent
from src.schemas.event import EventQuery
from src.schemas.stream import serialize_event
from src.utils.errors import not_found


def list_events(db: Session, stream_id: str, query: EventQuery) -> dict[str, Any]:
    q = db.query(CdcEvent).filter(CdcEvent.stream_id == stream_id)
    if query.op:
        q = q.filter(CdcEvent.op == query.op)
    if query.pk:
        q = q.filter(CdcEvent.pk_value == query.pk)
    if query.only_rejected:
        q = q.filter(CdcEvent.reject_reason.isnot(None))
    total = q.count()
    if query.order == "arrival":
        q = q.order_by(CdcEvent.received_seq.asc())
    elif query.order == "lsn_desc":
        q = q.order_by(CdcEvent.lsn.desc(), CdcEvent.received_seq.asc())
    else:
        # 同 LSN 的重复投递：原件（到达更早）排在副本前面，读起来才符合"去重保留第一份"
        q = q.order_by(CdcEvent.lsn.asc(), CdcEvent.received_seq.asc())
    rows = q.offset(query.offset).limit(query.limit).all()
    return {
        "items": [serialize_event(row) for row in rows],
        "total": int(total),
        "offset": query.offset,
        "limit": query.limit,
    }


def get_event(db: Session, event_id: str) -> CdcEvent:
    row = db.get(CdcEvent, event_id)
    if row is None:
        raise not_found("CdcEvent", event_id)
    return row


def diff_event(event: CdcEvent) -> dict[str, Any]:
    """before/after 字段级 diff：added / removed / changed / unchanged。"""
    before = event.before_json or {}
    after = event.after_json or {}
    keys = sorted(set(before) | set(after))
    added, removed, changed, unchanged = [], [], [], []
    for key in keys:
        in_before, in_after = key in before, key in after
        if not in_before and in_after:
            added.append({"field": key, "before": None, "after": after[key]})
        elif in_before and not in_after:
            removed.append({"field": key, "before": before[key], "after": None})
        elif before[key] != after[key]:
            changed.append({"field": key, "before": before[key], "after": after[key]})
        else:
            unchanged.append({"field": key, "before": before[key], "after": after[key]})
    return {
        "event": serialize_event(event),
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": unchanged,
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "unchanged": len(unchanged),
        },
    }


def arrival_order_stats(db: Session, stream_id: str) -> dict[str, Any]:
    """统计到达顺序与 LSN 顺序的逆序对数量：证明"乱序到达"是真实存在的。"""
    rows = (
        db.query(CdcEvent.lsn, CdcEvent.received_seq)
        .filter(CdcEvent.stream_id == stream_id)
        .order_by(CdcEvent.received_seq.asc())
        .all()
    )
    # 只统计"首次到达"的事件：重复投递天然带更小 LSN，不能算乱序
    inversions = 0
    previous_max = None
    seen: set[int] = set()
    for lsn, _seq in rows:
        if lsn in seen:
            continue
        seen.add(lsn)
        if previous_max is not None and lsn < previous_max:
            inversions += 1
        previous_max = lsn if previous_max is None else max(previous_max, lsn)
    duplicate_lsns = (
        db.query(func.count(CdcEvent.id))
        .filter(CdcEvent.stream_id == stream_id)
        .scalar()
        or 0
    ) - (
        db.query(func.count(func.distinct(CdcEvent.lsn)))
        .filter(CdcEvent.stream_id == stream_id)
        .scalar()
        or 0
    )
    return {
        "arrival_inversions": inversions,
        "duplicate_rows": int(duplicate_lsns),
        "event_rows": int(duplicate_lsns) + int(
            db.query(func.count(func.distinct(CdcEvent.lsn)))
            .filter(CdcEvent.stream_id == stream_id)
            .scalar()
            or 0
        ),
    }
