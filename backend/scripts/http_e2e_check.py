"""HTTP 端到端验证：登录 → 发起同窗口归并 → 轮询 → 校验发布详情与阻塞字段。"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000/api"
failures: list[str] = []


def call(method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        failures.append(name)


def wait_terminal(run_id: str, token: str, timeout_s: float = 30.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        detail = call("GET", f"/runs/{run_id}", token)
        if detail["status"] in {"succeeded", "failed", "canceled", "blocked"}:
            return detail
        time.sleep(0.8)
    raise TimeoutError(f"run {run_id} not terminal in {timeout_s}s")


def main() -> int:
    login = call("POST", "/auth/login", body={"email": "eng@cdc.local", "password": "Demo@2026"})
    token = login["access_token"]
    check("工程师登录成功", bool(token), f"role={login['user']['role']}")

    streams = call("GET", "/streams", token)
    stream_ids = {s["name"]: s["id"] for s in streams["items"]}
    check("拿到 orders / orders_breaking 两条流",
          {"orders", "orders_breaking"}.issubset(stream_ids), str(sorted(stream_ids)))

    # ---- 1) 正常流同窗口重跑：应成功发布、幂等、目标表行数不变 ----
    created = call("POST", "/runs", token, {
        "stream_id": stream_ids["orders"], "window_start_lsn": 1, "window_end_lsn": 37,
    })
    check("发起归并返回运行 id", bool(created.get("id")))
    detail = wait_terminal(created["id"], token)
    check("重跑状态 succeeded", detail["status"] == "succeeded", detail["status"])
    check("published=True 且目标表 18→18 行",
          detail["published"] is True and detail["target_rows_before"] == 18 and detail["target_rows_after"] == 18,
          f"{detail['target_rows_before']}->{detail['target_rows_after']}")
    pub = detail["publish"]
    check("发布详情含 LSN 守卫统计",
          pub["guarded_upserts"] == 0 and pub["stale_upserts_skipped"] == 18,
          f"upserts={pub['guarded_upserts']} skipped={pub['stale_upserts_skipped']}")
    check("目标表快照回读 18 行且带 _merge_lsn",
          len(pub["target_rows"]) == 18 and all(r.get("_merge_lsn") is not None for r in pub["target_rows"]))
    check("同窗口重跑标记幂等", detail.get("idempotent") is True)
    check("result.publish 与顶层 publish 一致", detail["result"]["publish"]["published"] is True)

    # ---- 2) 阻塞流重跑：blocked、未发布、列出阻塞字段、目标表为空 ----
    blocked_created = call("POST", "/runs", token, {
        "stream_id": stream_ids["orders_breaking"], "window_start_lsn": 1, "window_end_lsn": 3,
    })
    blocked = wait_terminal(blocked_created["id"], token)
    check("不兼容窗口状态 blocked", blocked["status"] == "blocked", blocked["status"])
    check("blocked 运行 published=False", blocked["published"] is False)
    bpub = blocked["publish"]
    check("阻塞原因=schema_gate 且列出阻塞字段",
          bpub["reason"] == "schema_gate" and len(bpub["blocking_fields"]) >= 3,
          f"reason={bpub['reason']} n={len(bpub['blocking_fields'])}")
    fields = {(b["field"], b["reason"]) for b in bpub["blocking_fields"]}
    check("阻塞字段覆盖 channel 缺列与 amount 类型冲突",
          ("channel", "unknown_column") in fields and ("amount", "type_incompatible") in fields,
          str(sorted(fields)))
    check("阻塞项带 LSN/主键/说明", all(b["lsn"] and b["detail"] for b in bpub["blocking_fields"]))

    # ---- 3) viewer 不能发起（403） ----
    viewer_login = call("POST", "/auth/login", body={"email": "viewer@cdc.local", "password": "Demo@2026"})
    viewer_token = viewer_login["access_token"]
    denied = False
    try:
        call("POST", "/runs", viewer_token, {
            "stream_id": stream_ids["orders"], "window_start_lsn": 1, "window_end_lsn": 1,
        })
    except urllib.error.HTTPError as exc:
        denied = exc.code == 403
    check("viewer 发起归并被 403 拒绝", denied)

    print()
    if failures:
        print(f"HTTP E2E FAILED {len(failures)}:", ", ".join(failures))
        return 1
    print("ALL HTTP E2E CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
