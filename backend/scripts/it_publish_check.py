"""集成验证（针对本地真实 PostgreSQL）：
1. 同一窗口重跑 -> 目标表唯一结果（行数/内容/digest 不变，全部 upsert 被 LSN 守卫跳过）；
2. 迟到旧事件 / 重复投递不能覆盖当前值（旧 LSN 的 update/delete 全部 no-op）；
3. 事务回滚 -> 目标表不留半批数据。
"""
from __future__ import annotations

import sys

from sqlalchemy import text

from src.config.database import session_scope
from src.models.merge_target import MergeTarget
from src.services.merge_engine import compute_merge
from src.services.target_publisher import MERGE_LSN_COLUMN, publish_window


def build_events() -> list[dict]:
    return [
        # LSN 1: insert ORD-A amount=100
        {"id": "e1", "lsn": 1, "received_seq": 1, "op": "insert", "pk_value": "ORD-A",
         "before_json": None,
         "after_json": {"order_id": "ORD-A", "member_id": "M-1", "amount": 100.0, "qty": 1,
                        "status": "paid", "updated_at": "2026-11-09T10:00:00"},
         "reject_reason": None, "reject_detail": None},
        # LSN 2: update ORD-A amount=200（最新位点，当前值应为 200）
        {"id": "e2", "lsn": 2, "received_seq": 2, "op": "update", "pk_value": "ORD-A",
         "before_json": {"amount": 100.0},
         "after_json": {"order_id": "ORD-A", "member_id": "M-1", "amount": 200.0, "qty": 1,
                        "status": "paid", "updated_at": "2026-11-09T10:05:00"},
         "reject_reason": None, "reject_detail": None},
        # LSN 1 的重复投递（同 lsn 同 pk），应在引擎层去重
        {"id": "e1-dup", "lsn": 1, "received_seq": 3, "op": "insert", "pk_value": "ORD-A",
         "before_json": None,
         "after_json": {"order_id": "ORD-A", "member_id": "M-1", "amount": 100.0, "qty": 1,
                        "status": "paid", "updated_at": "2026-11-09T10:00:00"},
         "reject_reason": None, "reject_detail": None},
        # LSN 3: insert ORD-B amount=50，随后 LSN 5 被 delete
        {"id": "e3", "lsn": 3, "received_seq": 4, "op": "insert", "pk_value": "ORD-B",
         "before_json": None,
         "after_json": {"order_id": "ORD-B", "member_id": "M-2", "amount": 50.0, "qty": 1,
                        "status": "pending", "updated_at": "2026-11-09T10:10:00"},
         "reject_reason": None, "reject_detail": None},
        # LSN 4: 迟到的旧 update（比 ORD-B 现有位点 3 还新？不，4>3 会生效；这里测 LSN2 对 ORD-A 的旧 update）
        {"id": "e4", "lsn": 4, "received_seq": 5, "op": "update", "pk_value": "ORD-A",
         "before_json": {"amount": 200.0},
         "after_json": {"order_id": "ORD-A", "member_id": "M-1", "amount": 999.0, "qty": 1,
                        "status": "paid", "updated_at": "2026-11-09T10:20:00"},
         "reject_reason": None, "reject_detail": None},
        # LSN 5: delete ORD-B
        {"id": "e5", "lsn": 5, "received_seq": 6, "op": "delete", "pk_value": "ORD-B",
         "before_json": {"order_id": "ORD-B"}, "after_json": None,
         "reject_reason": None, "reject_detail": None},
    ]


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
        if not cond:
            failures.append(name)

    with session_scope() as db:
        target = db.query(MergeTarget).filter(MergeTarget.name == "orders_dw").one()
        # 用独立的临时目标表，避免与 seed 的 18 行互相干扰
        db.execute(text("DROP TABLE IF EXISTS dw.it_publish_demo"))
        db.execute(text("CREATE TABLE dw.it_publish_demo (LIKE dw.orders_dw INCLUDING ALL)"))
        existing_target = db.query(MergeTarget).filter(MergeTarget.name == "it_publish_demo").one_or_none()
        if existing_target is not None:
            demo_target = existing_target
            demo_target.target_table = "dw.it_publish_demo"
        else:
            demo_target = MergeTarget(
                name="it_publish_demo", target_db="dw", target_table="dw.it_publish_demo",
                pk_column="order_id", strategy="upsert",
            )
            db.add(demo_target)
        db.flush()

        stream_id = db.execute(text("SELECT id FROM cdc.change_streams WHERE name='orders'")).scalar()
        events = build_events()
        result1 = compute_merge(events, pk_column="order_id", window_start=1, window_end=5)
        result1["stream_id"] = str(stream_id)
        check("引擎去重 1 条重复投递", result1["counts"]["duplicate"] == 1)
        check("引擎最终行数=1（ORD-B 被删除）", len(result1["rows"]) == 1, f"rows={[r['pk'] for r in result1['rows']]}")
        check("tombstone 含 ORD-B", [t["pk"] for t in result1["tombstones"]] == ["ORD-B"])

        pub1 = publish_window(db, demo_target, stream_id, result1)
        check("首次发布成功", pub1["published"] is True, str({k: pub1[k] for k in ("guarded_upserts", "guarded_deletes", "row_count_before", "row_count_after")}))
        # 最终行集只有 ORD-A（ORD-B 被 LSN5 删除），所以 1 次 upsert；delete 作用于发布前不存在的行，记为 skip
        check("首次发布 upsert=1，delete 无目标行被跳过", pub1["guarded_upserts"] == 1 and pub1["guarded_deletes"] == 0,
              f"upserts={pub1['guarded_upserts']} deletes={pub1['guarded_deletes']} skip_del={pub1['stale_deletes_skipped']}")

        rows = db.execute(text("SELECT order_id, amount, _merge_lsn FROM dw.it_publish_demo ORDER BY order_id")).all()
        check("目标表只剩 ORD-A 且 amount=999（LSN4 最新值）",
              [(r[0], float(r[1]), r[2]) for r in rows] == [("ORD-A", 999.0, 4)],
              str([tuple(r) for r in rows]))
        snapshot1 = db.execute(text("SELECT md5(string_agg(order_id||amount::text||COALESCE(_merge_lsn::text,''), '|' ORDER BY order_id)) FROM dw.it_publish_demo")).scalar()

        # ---- 同一窗口重跑：digest 相同，LSN 守卫让所有 upsert/delete 变 no-op ----
        result2 = compute_merge(events, pk_column="order_id", window_start=1, window_end=5)
        result2["stream_id"] = str(stream_id)
        check("重跑 digest 与首次一致", result1["digest"] == result2["digest"])
        pub2 = publish_window(db, demo_target, stream_id, result2)
        check("重跑仍判定发布成功", pub2["published"] is True)
        check("重跑唯一的最终行 upsert 被守卫跳过", pub2["stale_upserts_skipped"] == 1 and pub2["guarded_upserts"] == 0,
              f"upserts={pub2['guarded_upserts']} skipped={pub2['stale_upserts_skipped']}")
        check("重跑 delete 被守卫跳过（ORD-B 已不存在/位点不满足）",
              pub2["guarded_deletes"] == 0, f"deletes={pub2['guarded_deletes']} skip_del={pub2['stale_deletes_skipped']}")
        check("重跑前后行数不变 1 -> 1", pub2["row_count_before"] == 1 and pub2["row_count_after"] == 1)
        snapshot2 = db.execute(text("SELECT md5(string_agg(order_id||amount::text||COALESCE(_merge_lsn::text,''), '|' ORDER BY order_id)) FROM dw.it_publish_demo")).scalar()
        check("重跑后目标表内容完全一致", snapshot1 == snapshot2)
        check("回读快照行数=1", pub2["target_rows"] and len(pub2["target_rows"]) == 1)

        # ---- 迟到旧事件：手工塞一条 LSN=2 的 update（旧于当前位点 4），不能覆盖 999 ----
        stale_event = [{
            "id": "stale1", "lsn": 2, "received_seq": 9, "op": "update", "pk_value": "ORD-A",
            "before_json": {"amount": 100.0},
            "after_json": {"order_id": "ORD-A", "member_id": "M-1", "amount": 1.0, "qty": 1,
                           "status": "paid", "updated_at": "2026-11-09T09:00:00"},
            "reject_reason": None, "reject_detail": None,
        }]
        stale_result = compute_merge(stale_event, pk_column="order_id", window_start=2, window_end=2)
        stale_result["stream_id"] = str(stream_id)
        pub3 = publish_window(db, demo_target, stream_id, stale_result)
        amount = db.execute(text("SELECT amount FROM dw.it_publish_demo WHERE order_id='ORD-A'")).scalar()
        check("迟到旧事件未覆盖当前值（amount 仍为 999）", float(amount) == 999.0, f"amount={amount}")
        check("迟到旧事件 upsert 被跳过", pub3["stale_upserts_skipped"] == 1 and pub3["guarded_upserts"] == 0)
        lsn_now = db.execute(text("SELECT _merge_lsn FROM dw.it_publish_demo WHERE order_id='ORD-A'")).scalar()
        check("行位点仍停在 4，未被旧位点回退", lsn_now == 4, f"_merge_lsn={lsn_now}")

        # ---- 迟到旧 delete（LSN=3 删除 ORD-A，旧于当前位点 4）不生效 ----
        stale_del = [{
            "id": "stale-del", "lsn": 3, "received_seq": 10, "op": "delete", "pk_value": "ORD-A",
            "before_json": None, "after_json": None,
            "reject_reason": None, "reject_detail": None,
        }]
        del_result = compute_merge(stale_del, pk_column="order_id", window_start=3, window_end=3)
        del_result["stream_id"] = str(stream_id)
        pub4 = publish_window(db, demo_target, stream_id, del_result)
        remaining = db.execute(text("SELECT count(*) FROM dw.it_publish_demo WHERE order_id='ORD-A'")).scalar()
        check("迟到旧 delete 未删除当前行", remaining == 1, f"remaining={remaining}")
        check("旧 delete 被守卫跳过", pub4["stale_deletes_skipped"] == 1 and pub4["guarded_deletes"] == 0)

        # ---- 半批防护：gate 通过后在写入阶段异常时事务回滚，目标表回到发布前 ----
        # 先把当前状态提交，再用独立 session 触发失败，保证回滚只影响发布事务
        from src.config.database import SessionLocal

        db.commit()
        before_count = db.execute(text("SELECT count(*) FROM dw.it_publish_demo")).scalar()
        before_amount = float(db.execute(
            text("SELECT amount FROM dw.it_publish_demo WHERE order_id='ORD-A'")
        ).scalar())
        target_id = demo_target.id
        # 两条事件字段都能过 gate；第二行用超出 integer 范围的 qty 在 SQL 执行期才失败
        bad_result = {
            "rows": [
                {"pk": "ORD-A", "op": "update", "last_lsn": 10, "rebuilt": False,
                 "values": {"order_id": "ORD-A", "amount": 1.0, "updated_at": "2026-11-09T11:00:00"}},
                {"pk": "ORD-BAD", "op": "insert", "last_lsn": 11, "rebuilt": False,
                 "values": {"order_id": "ORD-BAD", "amount": 12.0, "qty": 99999999999999999999}},
            ],
            "tombstones": [],
            "applied_events": [
                {"event_id": "x1", "lsn": 10, "pk": "ORD-A", "op": "update",
                 "before": {}, "after": {"order_id": "ORD-A", "amount": 1.0}},
                {"event_id": "x2", "lsn": 11, "pk": "ORD-BAD", "op": "insert",
                 "before": {}, "after": {"order_id": "ORD-BAD", "amount": 12.0,
                                         "qty": 99999999999999999999}},
            ],
        }
        raised = False
        fail_session = SessionLocal()
        try:
            fail_target = fail_session.get(MergeTarget, target_id)
            publish_window(fail_session, fail_target, stream_id, bad_result)
        except Exception as exc:  # noqa: BLE001
            raised = True
            print("       预期内异常:", type(exc).__name__, str(exc).splitlines()[0][:120])
        finally:
            fail_session.close()
        check("发布异常被向上抛出", raised)
        # 失败事务已回滚；外层 session 开启新事务读到的应是回滚后的稳定状态
        db.expire_all()
        after_count = db.execute(text("SELECT count(*) FROM dw.it_publish_demo")).scalar()
        check("回滚后目标表行数与发布前一致（无半批）", before_count == after_count == 1,
              f"before={before_count} after={after_count}")
        amount = float(db.execute(
            text("SELECT amount FROM dw.it_publish_demo WHERE order_id='ORD-A'")
        ).scalar())
        check("回滚后 ORD-A 金额未被部分写入污染", amount == before_amount == 999.0,
              f"before={before_amount} after={amount}")
        bad_left = db.execute(text("SELECT count(*) FROM dw.it_publish_demo WHERE order_id='ORD-BAD'")).scalar()
        check("回滚后不存在半截写入的 ORD-BAD", bad_left == 0, f"bad_rows={bad_left}")

        # ---- 边界：载荷只含主键的 upsert（SET 子句不能缺业务列而语法报错）----
        pk_only = {
            "rows": [
                {"pk": "ORD-SOLO", "op": "insert", "last_lsn": 20, "rebuilt": False,
                 "values": {"order_id": "ORD-SOLO"}},
            ],
            "tombstones": [],
            "applied_events": [
                {"event_id": "solo1", "lsn": 20, "pk": "ORD-SOLO", "op": "insert",
                 "before": {}, "after": {"order_id": "ORD-SOLO"}},
            ],
        }
        solo_pub = publish_window(db, demo_target, stream_id, pk_only)
        solo_exists = db.execute(
            text("SELECT _merge_lsn FROM dw.it_publish_demo WHERE order_id='ORD-SOLO'")
        ).scalar()
        check("仅主键载荷可正常 upsert（其他列为 NULL）",
              solo_pub["published"] is True and solo_exists == 20, f"lsn={solo_exists}")

        db.execute(text("DROP TABLE dw.it_publish_demo"))

    print()
    if failures:
        print(f"FAILED {len(failures)}:", ", ".join(failures))
        return 1
    print("ALL INTEGRATION CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
