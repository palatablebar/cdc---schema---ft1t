"""日志模板集中登记（便于统一检索；main.py 导入触发一次登记检查）。"""
from __future__ import annotations

LOG_TEMPLATES: dict[str, str] = {
    "merge.start": "merge start run=%s stream=%s window=[%s,%s]",
    "merge.done": "merge done run=%s status=%s processed=%s duplicate=%s rejected=%s",
    "merge.fail": "merge fail run=%s error=%s",
    "schema.diff": "schema diff left=%s right=%s level=%s changes=%s",
    "replay.start": "replay start rejected=%s actor=%s",
    "replay.done": "replay done rejected=%s new_event=%s",
}
