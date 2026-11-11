"""幂等演示数据入口：`docker compose exec backend python -m scripts.seed_demo`。

自然键：
  ChangeStream.name / CdcEvent(stream_id, lsn, received_seq) / MergeTarget.name /
  SchemaVersion(stream_id, version_label) / MergeRun(stream_id, window, triggered_by is null) /
  RejectedEvent(stream_id, lsn, reason) / User.email

期望结果（orders 流窗口 [1,37]）：upsert 18 / duplicate 3 / rejected 2。
重复执行只打印 SEED_SKIPPED，并在末尾打印 SEED_SUMMARY {json} 供幂等校验。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from src.config.database import session_scope
from src.constants.enums import (
    CdcOp,
    MergeStrategy,
    RejectStatus,
    RunStatus,
    StreamStatus,
)
from src.constants.roles import ROLE_ADMIN, ROLE_ENGINEER, ROLE_VIEWER
from src.models.audit_log import AuditLog
from src.models.cdc_event import CdcEvent
from src.models.change_stream import ChangeStream
from src.models.merge_run import MergeRun
from src.models.merge_target import MergeTarget
from src.models.rejected_event import RejectedEvent
from src.models.schema_version import SchemaVersion
from src.models.user import User
from src.services.merge_engine import compute_merge
from src.utils.password import hash_password

DEMO_PASSWORD = "Demo@2026"
DEMO_USERS = [
    ("admin@cdc.local", "北岸生活 · 平台管理员", ROLE_ADMIN),
    ("eng@cdc.local", "北岸生活 · 数据工程师", ROLE_ENGINEER),
    ("viewer@cdc.local", "北岸生活 · 分析师", ROLE_VIEWER),
]

BASE_TIME = datetime(2026, 11, 9, 22, 0, 0, tzinfo=timezone.utc)

ORDER_IDS = [f"ORD-20261109-{1000 + index}" for index in range(1, 19)]
CUSTOMER_IDS = [f"C-202611-{index:03d}" for index in range(1, 11)]

ORDERS_SCHEMA_V1 = [
    {"name": "order_id", "type": "text", "nullable": False, "default": None, "is_pk": True},
    {"name": "member_id", "type": "text", "nullable": True, "default": None, "is_pk": False},
    {"name": "amount", "type": "numeric(14,2)", "nullable": True, "default": None, "is_pk": False},
    {"name": "qty", "type": "integer", "nullable": True, "default": None, "is_pk": False},
    {"name": "status", "type": "text", "nullable": False, "default": "pending", "is_pk": False},
    {"name": "updated_at", "type": "timestamp", "nullable": False, "default": None, "is_pk": False},
]

ORDERS_SCHEMA_V2 = [
    {"name": "order_id", "type": "text", "nullable": False, "default": None, "is_pk": True},
    {"name": "member_id", "type": "text", "nullable": True, "default": None, "is_pk": False},
    {"name": "amount", "type": "numeric(12,2)", "nullable": True, "default": None, "is_pk": False},
    {"name": "qty", "type": "integer", "nullable": True, "default": None, "is_pk": False},
    {"name": "status", "type": "text", "nullable": False, "default": "pending", "is_pk": False},
    {"name": "updated_at", "type": "timestamp", "nullable": False, "default": None, "is_pk": False},
    {"name": "channel", "type": "text", "nullable": True, "default": None, "is_pk": False},
]

CUSTOMERS_SCHEMA_V1 = [
    {"name": "customer_id", "type": "text", "nullable": False, "default": None, "is_pk": True},
    {"name": "mobile", "type": "text", "nullable": True, "default": None, "is_pk": False},
    {"name": "tier", "type": "text", "nullable": False, "default": "basic", "is_pk": False},
    {"name": "city", "type": "text", "nullable": True, "default": None, "is_pk": False},
    {"name": "updated_at", "type": "timestamp", "nullable": False, "default": None, "is_pk": False},
]

CREATED = 0
SKIPPED = 0


def _log(kind: str, entity: str, key: str) -> None:
    global CREATED, SKIPPED
    if kind == "SEED_CREATED":
        CREATED += 1
    else:
        SKIPPED += 1
    print(f"{kind} entity={entity} key={key}", flush=True)


def _created(entity: str, key: str) -> None:
    _log("SEED_CREATED", entity, key)


def _skipped(entity: str, key: str) -> None:
    _log("SEED_SKIPPED", entity, key)


# ------------------------------------------------------------------ 账号 ----


def seed_users(db) -> dict[str, User]:
    users: dict[str, User] = {}
    for email, display_name, role in DEMO_USERS:
        user = db.query(User).filter(User.email == email).one_or_none()
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password(DEMO_PASSWORD),
                display_name=display_name,
                role=role,
                is_active=True,
            )
            db.add(user)
            db.flush()
            _created("User", email)
        else:
            _skipped("User", email)
        users[role] = user
    db.commit()
    return users


# ------------------------------------------------------------------ 事件 ----


def build_orders_events() -> list[dict[str, Any]]:
    """39 条唯一 LSN 的 orders 事件 + 3 条重复投递。"""
    events: list[dict[str, Any]] = []
    state: dict[str, dict[str, Any]] = {}

    def emit(lsn: int, op: str, pk: str | None, before: dict | None, after: dict | None) -> None:
        events.append(
            {
                "lsn": lsn,
                "op": op,
                "pk_value": pk,
                "before": before,
                "after": after,
                "reject_reason": None,
                "reject_detail": None,
            }
        )

    # 1) 18 条 insert（LSN 1..18）
    for index, order_id in enumerate(ORDER_IDS, start=1):
        after = {
            "order_id": order_id,
            "member_id": f"M-{(index % 7) + 1:04d}",
            "amount": round(120.0 + index * 7.25, 2),
            "qty": (index % 4) + 1,
            "status": "paid" if index % 3 else "pending",
            "updated_at": f"2026-11-09T{8 + (index % 10):02d}:{(index * 7) % 60:02d}:00",
        }
        state[order_id] = dict(after)
        emit(index, CdcOp.INSERT.value, order_id, None, dict(after))

    lsn = 19

    # 2) 17 条 update（LSN 19..35）：pk1/pk2 各两条（其中一条只改状态），pk3 两条，pk4..pk14 各一条
    def update(order_id: str, field: str, delta: float | None = None, value: Any = None) -> None:
        nonlocal lsn
        before = dict(state[order_id])
        after = dict(before)
        if delta is not None:
            after[field] = round(float(before[field]) + delta, 2)
        else:
            after[field] = value
        after["updated_at"] = f"2026-11-09T23:{lsn % 60:02d}:00"
        state[order_id] = after
        emit(lsn, CdcOp.UPDATE.value, order_id, before, after)
        lsn += 1

    update(ORDER_IDS[0], "amount", delta=12.5)
    update(ORDER_IDS[0], "amount", delta=7.5)
    update(ORDER_IDS[1], "amount", delta=20.0)
    update(ORDER_IDS[1], "status", value="shipped")
    update(ORDER_IDS[2], "qty", value=state[ORDER_IDS[2]]["qty"] + 1)
    update(ORDER_IDS[2], "amount", delta=5.0)
    for order_id in ORDER_IDS[3:14]:
        update(order_id, "amount", delta=3.0)

    # 3) 4 条拒绝事件（LSN 36..39），覆盖 4 种原因枚举
    emit(36, CdcOp.UPDATE.value, "ORD-20261109-1090", None, {
        "order_id": "ORD-20261109-1090",
        "member_id": "M-0011",
        "amount": "1,280.00",
        "qty": 2,
        "status": "paid",
        "updated_at": "2026-11-09T23:41:00",
    })
    events[-1]["reject_reason"] = "type_conflict"
    events[-1]["reject_detail"] = "字段 amount 期望 numeric，实际收到带千分位的字符串 '1,280.00'"

    emit(37, CdcOp.UPDATE.value, "ORD-20261109-1091", None, {
        "order_id": "ORD-20261109-1091",
        "member_id": "M-0005",
        "amount": 640.0,
        "qty": 1,
        "updated_at": "2026-11-09T23:42:00",
    })
    events[-1]["reject_reason"] = "schema_mismatch"
    events[-1]["reject_detail"] = "缺少非空列 status（schema v2 默认 'pending'，需重放补齐）"

    emit(38, CdcOp.UPDATE.value, "ORD-20261109-1092", None, {
        "order_id": "ORD-20261109-1092",
        "amount": "¥980.50",
        "qty": "3",
        "updated_at": "2026-11-09T23:43:00",
    })
    events[-1]["reject_reason"] = "parse_error"
    events[-1]["reject_detail"] = "载荷含货币符号与非数字 qty，JSON 解析后无法直接落账"

    emit(39, CdcOp.UPDATE.value, None, None, {
        "member_id": "M-0009",
        "amount": 88.0,
        "qty": 1,
        "status": "paid",
        "updated_at": "2026-11-09T23:44:00",
    })
    events[-1]["reject_reason"] = "pk_missing"
    events[-1]["reject_detail"] = "事件缺少主键 order_id，无法确定落账目标"

    # 4) 3 条重复投递（同 stream + 同 lsn + 同 pk），排在到达序列末尾
    for duplicate_lsn in (1, 19, 25):
        source = next(item for item in events if item["lsn"] == duplicate_lsn)
        events.append(
            {
                "lsn": source["lsn"],
                "op": source["op"],
                "pk_value": source["pk_value"],
                "before": source["before"],
                "after": source["after"],
                "reject_reason": source["reject_reason"],
                "reject_detail": source["reject_detail"],
            }
        )
    return events


def arrival_order(unique_count: int) -> list[int]:
    """到达顺序：在 LSN 顺序上做两处相邻对调，制造恰好 2 处「乱序投递」。

    对调只改变到达顺序、不改变事件集合，因此归并结果与 digest 不变；
    这正好用来证明「到达顺序不影响落账结果」。
    """
    order = list(range(1, unique_count + 1))
    for left, right in ((18, 19), (27, 28)):
        i, j = order.index(left), order.index(right)
        order[i], order[j] = order[j], order[i]
    return order


def build_customers_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    state: dict[str, dict[str, Any]] = {}
    for index, customer_id in enumerate(CUSTOMER_IDS, start=1):
        after = {
            "customer_id": customer_id,
            "mobile": f"138{index:08d}",
            "tier": ["gold", "silver", "basic"][index % 3],
            "city": ["上海", "杭州", "宁波", "苏州"][index % 4],
            "updated_at": f"2026-11-09T{9 + index % 10:02d}:{index * 5 % 60:02d}:00",
        }
        state[customer_id] = dict(after)
        events.append(
            {
                "lsn": index,
                "op": CdcOp.INSERT.value,
                "pk_value": customer_id,
                "before": None,
                "after": dict(after),
                "reject_reason": None,
                "reject_detail": None,
            }
        )
    # LSN 11/12 两条 update
    for offset, (customer_index, field, value) in enumerate(
        [(0, "city", "无锡"), (1, "tier", "gold")], start=11
    ):
        customer_id = CUSTOMER_IDS[customer_index]
        before = dict(state[customer_id])
        after = dict(before)
        after[field] = value
        after["updated_at"] = f"2026-11-09T23:{offset:02d}:00"
        state[customer_id] = after
        events.append(
            {
                "lsn": offset,
                "op": CdcOp.UPDATE.value,
                "pk_value": customer_id,
                "before": before,
                "after": after,
                "reject_reason": None,
                "reject_detail": None,
            }
        )
    # LSN 13/14 两条拒绝
    events.append(
        {
            "lsn": 13,
            "op": CdcOp.UPDATE.value,
            "pk_value": "C-202611-011",
            "before": None,
            "after": {"customer_id": "C-202611-011", "mobile": "13900000011", "tier": 3,
                      "city": "南京", "updated_at": "2026-11-09T23:50:00"},
            "reject_reason": "type_conflict",
            "reject_detail": "tier 期望 text，实际收到整数 3",
        }
    )
    events.append(
        {
            "lsn": 14,
            "op": CdcOp.UPDATE.value,
            "pk_value": "C-202611-012",
            "before": None,
            "after": {"customer_id": "C-202611-012", "mobile": "13900000012",
                      "city": "合肥", "updated_at": "2026-11-09T23:51:00"},
            "reject_reason": "schema_mismatch",
            "reject_detail": "缺少非空列 tier（默认 'basic'，需重放补齐）",
        }
    )
    return events


def seed_stream(db, spec: dict[str, Any]) -> ChangeStream:
    stream = db.query(ChangeStream).filter(ChangeStream.name == spec["name"]).one_or_none()
    if stream is not None:
        _skipped("ChangeStream", spec["name"])
        return stream
    stream = ChangeStream(
        name=spec["name"],
        source_db=spec["source_db"],
        source_table=spec["source_table"],
        pk_column=spec["pk_column"],
        watermark_lsn=0,
        max_lsn=0,
        status=spec["status"],
        description=spec["description"],
        owner_team=spec["owner_team"],
    )
    db.add(stream)
    db.flush()
    _created("ChangeStream", spec["name"])
    return stream


def seed_events(
    db,
    stream: ChangeStream,
    events: list[dict[str, Any]],
    arrival: list[int],
    duplicate_lsns: list[int],
) -> dict[int, CdcEvent]:
    """按到达顺序插入事件；返回 lsn -> 第一条事件的索引。"""
    existing = (
        db.query(CdcEvent)
        .filter(CdcEvent.stream_id == stream.id)
        .order_by(CdcEvent.lsn.asc(), CdcEvent.received_seq.asc())
        .all()
    )
    if existing:
        _skipped("CdcEvent", f"{stream.name}:{len(existing)}")
        return {row.lsn: row for row in existing}

    by_lsn: dict[int, list[dict[str, Any]]] = {}
    for event in events:
        by_lsn.setdefault(event["lsn"], []).append(event)

    created: dict[int, CdcEvent] = {}
    seq = 0
    for lsn in arrival:
        candidates = by_lsn.get(lsn, [])
        if not candidates:
            continue
        payload = candidates[0]
        seq += 1
        row = CdcEvent(
            stream_id=stream.id,
            lsn=payload["lsn"],
            received_seq=seq,
            op=payload["op"],
            pk_value=payload["pk_value"],
            before_json=payload["before"],
            after_json=payload["after"],
            reject_reason=payload["reject_reason"],
            reject_detail=payload["reject_detail"],
            received_at=BASE_TIME + timedelta(minutes=seq),
        )
        db.add(row)
        db.flush()
        created.setdefault(payload["lsn"], row)
        _created("CdcEvent", f"{stream.name}:lsn={payload['lsn']}:seq={seq}")

    # 重复投递：同一 LSN 的第二份载荷（只对 orders 流注入）
    for duplicate_lsn in duplicate_lsns:
        source = by_lsn[duplicate_lsn][0]
        seq += 1
        row = CdcEvent(
            stream_id=stream.id,
            lsn=duplicate_lsn,
            received_seq=seq,
            op=source["op"],
            pk_value=source["pk_value"],
            before_json=source["before"],
            after_json=source["after"],
            reject_reason=None,
            reject_detail=None,
            received_at=BASE_TIME + timedelta(minutes=seq),
        )
        db.add(row)
        db.flush()
        _created("CdcEvent", f"{stream.name}:lsn={duplicate_lsn}:dup:seq={seq}")

    stream.max_lsn = max(event["lsn"] for event in events)
    stream.last_event_at = BASE_TIME + timedelta(minutes=seq)
    db.commit()
    return created


def seed_schema_versions(db, stream: ChangeStream, versions: list[tuple[str, list[dict], str, str]]) -> dict[str, SchemaVersion]:
    result: dict[str, SchemaVersion] = {}
    for label, fields, summary, created_by in versions:
        row = (
            db.query(SchemaVersion)
            .filter(SchemaVersion.stream_id == stream.id, SchemaVersion.version_label == label)
            .one_or_none()
        )
        if row is None:
            row = SchemaVersion(
                stream_id=stream.id,
                version_label=label,
                fields_json=fields,
                ddl_summary=summary,
                created_by=created_by,
            )
            db.add(row)
            db.flush()
            _created("SchemaVersion", f"{stream.name}:{label}")
        else:
            _skipped("SchemaVersion", f"{stream.name}:{label}")
        result[label] = row
    db.commit()
    return result


def seed_targets(db) -> dict[str, MergeTarget]:
    specs = [
        ("orders_dw", "dw.orders_dw", "order_id", "orders 流落地表：按 order_id upsert，金额为业务口径的最终值"),
        ("customers_dw", "dw.customers_dw", "customer_id", "customers 流落地表：维表，按 customer_id upsert"),
    ]
    result: dict[str, MergeTarget] = {}
    for name, table, pk, description in specs:
        row = db.query(MergeTarget).filter(MergeTarget.name == name).one_or_none()
        if row is None:
            row = MergeTarget(
                name=name,
                target_db="dw",
                target_table=table,
                pk_column=pk,
                strategy=MergeStrategy.UPSERT.value,
                description=description,
            )
            db.add(row)
            db.flush()
            _created("MergeTarget", name)
        else:
            _skipped("MergeTarget", name)
        result[name] = row
    db.commit()
    return result


def seed_merge_run(db, stream: ChangeStream, target: MergeTarget) -> MergeRun | None:
    # 只认 seed 自己那条运行（triggered_by 为空且窗口固定）；用户通过页面发起的运行不算重复
    existing = (
        db.query(MergeRun)
        .filter(
            MergeRun.stream_id == stream.id,
            MergeRun.triggered_by.is_(None),
            MergeRun.window_start_lsn == 1,
            MergeRun.window_end_lsn == 37,
        )
        .order_by(MergeRun.created_at.asc())
        .first()
    )
    if existing is not None:
        _skipped("MergeRun", f"{stream.name}:seed-run")
        return existing

    events = db.query(CdcEvent).filter(CdcEvent.stream_id == stream.id).all()
    payload = [
        {
            "id": str(row.id),
            "lsn": row.lsn,
            "received_seq": row.received_seq,
            "op": row.op,
            "pk_value": row.pk_value,
            "before_json": row.before_json,
            "after_json": row.after_json,
            "reject_reason": row.reject_reason,
            "reject_detail": row.reject_detail,
        }
        for row in events
        if 1 <= row.lsn <= 37
    ]
    started = datetime.now(timezone.utc)
    result = compute_merge(
        payload,
        pk_column=stream.pk_column,
        strategy=MergeStrategy.UPSERT.value,
        window_start=1,
        window_end=37,
    )
    finished = datetime.now(timezone.utc)

    counts = result["counts"]
    run = MergeRun(
        stream_id=stream.id,
        target_id=target.id,
        window_start_lsn=1,
        window_end_lsn=37,
        status=RunStatus.SUCCEEDED.value,
        watermark_before=0,
        received_count=counts["received"],
        processed_count=counts["processed"],
        duplicate_count=counts["duplicate"],
        rejected_count=counts["rejected"],
        inserted_count=counts["inserted"],
        updated_count=counts["updated"],
        deleted_count=counts["deleted"],
        upserted_count=counts["upserted"],
        watermark_after=result["watermark_after"],
        duration_ms=max(1, int((finished - started).total_seconds() * 1000)),
        result_digest=result["digest"],
        result_json={**result, "triggered_by_label": "seed", "idempotent": False},
        created_at=finished,
        started_at=started,
        finished_at=finished,
    )
    db.add(run)
    db.flush()
    stream.watermark_lsn = result["watermark_after"]
    db.commit()
    _created("MergeRun", f"{stream.name}:[1,37] upsert={counts['upserted']}")
    return run


def seed_rejected(db, stream: ChangeStream, run: MergeRun | None) -> None:
    rows = (
        db.query(CdcEvent)
        .filter(CdcEvent.stream_id == stream.id, CdcEvent.reject_reason.isnot(None))
        .order_by(CdcEvent.lsn.asc())
        .all()
    )
    for row in rows:
        exists = (
            db.query(RejectedEvent)
            .filter(
                RejectedEvent.stream_id == stream.id,
                RejectedEvent.lsn == row.lsn,
                RejectedEvent.reason == row.reject_reason,
            )
            .one_or_none()
        )
        if exists is not None:
            _skipped("RejectedEvent", f"{stream.name}:lsn={row.lsn}")
            continue
        in_window = run is not None and run.window_start_lsn <= row.lsn <= run.window_end_lsn
        rejected = RejectedEvent(
            event_id=row.id,
            run_id=run.id if in_window else None,
            stream_id=stream.id,
            lsn=row.lsn,
            reason=row.reject_reason,
            detail=row.reject_detail or "",
            payload_json={
                "op": row.op,
                "pk_value": row.pk_value,
                "before": row.before_json,
                "after": row.after_json,
            },
            status=RejectStatus.PENDING.value,
        )
        db.add(rejected)
        db.flush()
        _created("RejectedEvent", f"{stream.name}:lsn={row.lsn}")
    db.commit()


def seed_audit(db, users: dict[str, User], streams: dict[str, ChangeStream]) -> None:
    if db.query(AuditLog).count() > 0:
        _skipped("AuditLog", "existing")
        return
    admin = users[ROLE_ADMIN]
    engineer = users[ROLE_ENGINEER]
    entries = [
        ("stream.create", "ChangeStream", str(streams["orders"].id), admin, {"name": "orders"}),
        ("stream.create", "ChangeStream", str(streams["customers"].id), admin, {"name": "customers"}),
        ("schema.diff", "SchemaVersion", "v1->v2", engineer, {"compat_level": "breaking", "change_count": 2}),
        ("run.trigger", "MergeRun", "seed", engineer, {"window": [1, 37]}),
    ]
    for action, entity_type, entity_id, actor, payload in entries:
        db.add(
            AuditLog(
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                actor_id=actor.id,
                payload_json=payload,
            )
        )
        _created("AuditLog", action)
    db.commit()


# ------------------------------------------------------------------ 汇总 ----


ENTITY_TABLES = {
    "change_stream": "change_streams",
    "cdc_event": "cdc_events",
    "merge_target": "merge_targets",
    "schema_version": "schema_versions",
    "merge_run": "merge_runs",
    "rejected_event": "rejected_events",
}


def summary_counts(db) -> dict[str, int]:
    from src.config.settings import settings

    counts: dict[str, int] = {}
    for label, table in ENTITY_TABLES.items():
        value = db.execute(text(f"SELECT count(*) FROM {settings.cdc_schema}.{table}")).scalar()
        counts[label] = int(value or 0)
    return counts


def seed_all() -> dict[str, Any]:
    global CREATED, SKIPPED
    CREATED = 0
    SKIPPED = 0
    with session_scope() as db:
        users = seed_users(db)

        orders = seed_stream(
            db,
            {
                "name": "orders",
                "source_db": "shop_mysql",
                "source_table": "shop.orders",
                "pk_column": "order_id",
                "status": StreamStatus.HEALTHY.value,
                "description": "交易主表增量流：日订单 40 万，binlog 经 Kafka 投递",
                "owner_team": "北岸生活 · 交易平台组",
            },
        )
        customers = seed_stream(
            db,
            {
                "name": "customers",
                "source_db": "shop_mysql",
                "source_table": "shop.customers",
                "pk_column": "customer_id",
                "status": StreamStatus.LAGGING.value,
                "description": "会员维表增量流：水位置空，等待首次全量对齐",
                "owner_team": "北岸生活 · 会员组",
            },
        )
        streams = {"orders": orders, "customers": customers}

        orders_events = build_orders_events()
        seed_events(db, orders, orders_events, arrival_order(39), [1, 19, 25])
        customers_events = build_customers_events()
        seed_events(db, customers, customers_events, list(range(1, 15)), [])

        seed_schema_versions(
            db,
            orders,
            [
                ("v1", ORDERS_SCHEMA_V1, "order_id PK; amount numeric(14,2); status text NOT NULL DEFAULT 'pending'", "dba@cdc.local"),
                ("v2", ORDERS_SCHEMA_V2, "新增 channel text；amount 收窄为 numeric(12,2)", "dba@cdc.local"),
            ],
        )
        seed_schema_versions(
            db,
            customers,
            [("v1", CUSTOMERS_SCHEMA_V1, "customer_id PK; tier text NOT NULL DEFAULT 'basic'", "dba@cdc.local")],
        )

        targets = seed_targets(db)
        run = seed_merge_run(db, orders, targets["orders_dw"])

        # 拒绝事件要在 run 之后落，才能带上 run_id
        seed_rejected(db, orders, run)
        seed_rejected(db, customers, None)

        seed_audit(db, users, streams)

        db.flush()
        counts = summary_counts(db)
        payload = {"created": CREATED, "skipped": SKIPPED, "counts": counts}
        print("SEED_SUMMARY " + json.dumps(counts, sort_keys=True, ensure_ascii=False), flush=True)
        return payload


if __name__ == "__main__":
    result = seed_all()
    print(
        f"SEED_DONE created={result['created']} skipped={result['skipped']}",
        flush=True,
    )
    sys.exit(0)
