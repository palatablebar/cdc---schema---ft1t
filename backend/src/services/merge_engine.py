"""算法 1：乱序/重复 CDC 事件的去重归并（纯函数，无 IO）。

输入：一个 LSN 窗口内的原始事件列表（到达顺序可能乱序、可能重复）。
处理：
  1. 按 (lsn, received_seq) 稳定排序，重复项判定键 = (lsn, pk_value)，保留最先到达的一份；
  2. 带 reject_reason 的事件计入 rejected，不落账；
  3. 按 LSN 顺序应用 insert / update / delete：
       - update 命中不存在或已删除的行时按 upsert 处理（delete 后再 insert 视为重建）；
       - delete 记 tombstone，最终行数不含它；
       - update 的 before 与当前行不一致时记 conflict（不阻断，但计入 conflicted）；
  4. 金额守恒校验：同 PK 的 amount 满足 `insert 值 + Σ(after-before) == 最终值`；
  5. 水位线 = 窗口内最小未到达 LSN 的前一个 LSN（有空洞时如实停在水位线处）。

输出：计数、最终行、冲突明细、金额校验、digest（用于幂等判定）。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from src.constants.enums import MergeStrategy
from src.utils.lsn import LsnWindow, first_gap


def _canonical(payload: dict[str, Any] | None) -> str:
    return json.dumps(payload or {}, sort_keys=True, ensure_ascii=False, default=str)


def _numeric(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def compute_merge(
    events: list[dict[str, Any]],
    pk_column: str,
    strategy: str = MergeStrategy.UPSERT.value,
    window_start: int = 1,
    window_end: int = 0,
) -> dict[str, Any]:
    window = LsnWindow(start=window_start, end=window_end)

    ordered = sorted(events, key=lambda row: (int(row["lsn"]), int(row["received_seq"])))

    seen_keys: set[tuple[int, str]] = set()
    seen_lsns: set[int] = set()
    duplicate_events: list[dict[str, Any]] = []
    rejected_events: list[dict[str, Any]] = []

    rows: dict[str, dict[str, Any]] = {}
    tombstones: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    amount_audit: dict[str, dict[str, Any]] = {}

    inserted = updated = deleted = rebuilt = 0

    for event in ordered:
        lsn = int(event["lsn"])
        pk_value = event.get("pk_value")
        dedupe_key = (lsn, str(pk_value))
        if dedupe_key in seen_keys:
            duplicate_events.append(
                {
                    "event_id": str(event.get("id", "")),
                    "lsn": lsn,
                    "pk": str(pk_value),
                    "kept_from": seen_keys_first_source(ordered, lsn, str(pk_value)),
                }
            )
            continue
        seen_keys.add(dedupe_key)
        seen_lsns.add(lsn)

        if event.get("reject_reason"):
            rejected_events.append(
                {
                    "event_id": str(event.get("id", "")),
                    "lsn": lsn,
                    "pk": str(pk_value) if pk_value is not None else None,
                    "reason": event["reject_reason"],
                    "detail": event.get("reject_detail") or "",
                }
            )
            continue

        if strategy == MergeStrategy.APPEND.value:
            # append 模式不做去重后的行合并，仅按插入计数，供对照演示
            inserted += 1
            continue

        if pk_value in (None, ""):
            rejected_events.append(
                {
                    "event_id": str(event.get("id", "")),
                    "lsn": lsn,
                    "pk": None,
                    "reason": "pk_missing",
                    "detail": f"事件缺少主键列 {pk_column}",
                }
            )
            continue

        pk = str(pk_value)
        op = event.get("op")
        after = dict(event.get("after_json") or {})
        before = dict(event.get("before_json") or {})

        if op == "insert":
            if pk in tombstones:
                rebuilt += 1
                tombstones.pop(pk)
                rows[pk] = {"values": after, "last_lsn": lsn, "op": "insert", "rebuilt": True}
                inserted += 1
            elif pk in rows:
                _merge_values(rows[pk], after, before, lsn, conflicts, pk)
                updated += 1
            else:
                rows[pk] = {"values": after, "last_lsn": lsn, "op": "insert", "rebuilt": False}
                inserted += 1
                amount_audit[pk] = {"base": _numeric(after.get("amount")), "deltas": [], "mismatch": False}

        elif op == "update":
            if pk in tombstones:
                rebuilt += 1
                tombstones.pop(pk)
                rows[pk] = {"values": after, "last_lsn": lsn, "op": "update", "rebuilt": True}
                inserted += 1
                amount_audit[pk] = {"base": _numeric(after.get("amount")), "deltas": [], "mismatch": False}
            elif pk not in rows:
                rows[pk] = {"values": after, "last_lsn": lsn, "op": "update", "rebuilt": False}
                inserted += 1
                amount_audit[pk] = {"base": _numeric(after.get("amount")), "deltas": [], "mismatch": False}
            else:
                _merge_values(rows[pk], after, before, lsn, conflicts, pk)
                updated += 1
                audit = amount_audit.setdefault(pk, {"base": None, "deltas": [], "mismatch": False})
                before_amount = _numeric(before.get("amount"))
                after_amount = _numeric(after.get("amount"))
                if before_amount is not None and after_amount is not None:
                    audit["deltas"].append(round(after_amount - before_amount, 4))

        elif op == "delete":
            rows.pop(pk, None)
            tombstones[pk] = {"pk": pk, "last_lsn": lsn}
            deleted += 1
        else:
            rejected_events.append(
                {
                    "event_id": str(event.get("id", "")),
                    "lsn": lsn,
                    "pk": pk,
                    "reason": "parse_error",
                    "detail": f"未知操作类型 {op!r}",
                }
            )

    for pk, audit in amount_audit.items():
        if audit["base"] is None:
            continue
        expected = audit["base"] + sum(audit["deltas"])
        final_row = rows.get(pk)
        actual = _numeric((final_row or {}).get("values", {}).get("amount"))
        if actual is None:
            audit["expected"] = round(expected, 4)
            audit["actual"] = None
            audit["mismatch"] = bool(audit["deltas"])
        else:
            audit["expected"] = round(expected, 4)
            audit["actual"] = round(actual, 4)
            audit["mismatch"] = abs(expected - actual) > 1e-6

    gap = first_gap(seen_lsns, window)
    watermark_after = (gap - 1) if gap is not None else window.end

    result_rows = []
    for pk in sorted(rows):
        entry = rows[pk]
        result_rows.append(
            {
                "pk": pk,
                "op": "insert" if entry["op"] == "insert" else "update",
                "last_lsn": entry["last_lsn"],
                "rebuilt": entry["rebuilt"],
                "values": entry["values"],
            }
        )

    counts = {
        "received": len(events),
        "processed": inserted + updated + deleted,
        "inserted": inserted,
        "updated": updated,
        "deleted": deleted,
        "rebuilt": rebuilt,
        "upserted": len(result_rows),
        "duplicate": len(duplicate_events),
        "rejected": len(rejected_events),
        "conflicted": len(conflicts),
    }
    amount_result = {
        "checked": len([a for a in amount_audit.values() if a["base"] is not None]),
        "mismatched": len([a for a in amount_audit.values() if a.get("mismatch")]),
        "items": [
            {"pk": pk, **{k: v for k, v in audit.items() if k != "deltas"}, "delta_sum": round(sum(audit["deltas"]), 4)}
            for pk, audit in sorted(amount_audit.items())
            if audit["base"] is not None
        ],
    }

    digest_payload = {
        "window": window.as_dict(),
        "strategy": strategy,
        "counts": counts,
        "watermark_after": watermark_after,
        "rows": [{"pk": r["pk"], "last_lsn": r["last_lsn"], "values": r["values"]} for r in result_rows],
    }
    digest = "sha256:" + hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()

    return {
        "window": window.as_dict(),
        "strategy": strategy,
        "counts": counts,
        "watermark_after": watermark_after,
        "gap": gap,
        "rows": result_rows,
        "conflicts": conflicts,
        "duplicates": duplicate_events,
        "rejected": rejected_events,
        "amount_audit": amount_result,
        "digest": digest,
    }


def _merge_values(
    row: dict[str, Any],
    after: dict[str, Any],
    before: dict[str, Any],
    lsn: int,
    conflicts: list[dict[str, Any]],
    pk: str,
) -> None:
    current = row["values"]
    # before 与当前行不一致 = 上游视图过期，记录下来供人工核对
    for key, value in before.items():
        if key in current and current[key] != value:
            conflicts.append(
                {
                    "pk": pk,
                    "field": key,
                    "lsn": lsn,
                    "before_value": value,
                    "current_value": current[key],
                    "after_value": after.get(key),
                }
            )
    changed = {k: v for k, v in after.items() if current.get(k) != v}
    current.update(after)
    row["last_lsn"] = lsn
    row["op"] = "update"
    row.setdefault("changed_fields", []).extend(sorted(changed))


def seen_keys_first_source(ordered: list[dict[str, Any]], lsn: int, pk: str) -> str | None:
    for event in ordered:
        if int(event["lsn"]) == lsn and str(event.get("pk_value")) == pk:
            return str(event.get("id", ""))
    return None
