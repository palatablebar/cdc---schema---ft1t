# cdcmerge · CDC 变更流增量合并与 schema 演进工作台

> 北岸生活（跨境零售）数据平台组的值班管制台：把上游 binlog 事件乱序去重地归并落账，并在上游改字段时判定 schema 兼容等级、生成迁移与回滚 SQL。

## 1. 真实场景

- **模拟客户**：跨境零售「北岸生活」数据平台组（8 人）。日订单 40 万，业务库 MySQL 的 binlog 经 CDC 投递到 Kafka，再进数仓。
- **现有工作流**：DBA 每晚全量导出 + 人工 SQL 对账。
- **三个痛点**：
  1. 夜间窗口跑不完，白天查不到增量；
  2. 上游改字段后下游报表整列报错；
  3. 重复投递 / 乱序事件导致金额翻倍，回滚靠手工 `DELETE`。
- **上下游**：上游 MySQL binlog（本 demo 以事件表 + REST 模拟）→ 本系统做「事件落账 + 顺序归并 + schema 兼容判定」→ 下游 dbt 报表与风控。
- **角色权限**：

| 角色 | 枚举 | 主要页面 | 典型动作 |
|---|---|---|---|
| 平台管理员 | `admin` | 全部 | 建流、改目标表、回滚、重置水位线 |
| 数据工程师 | `engineer` | 看板/事件/运行/拒绝重放/schema | 发起合并运行、重放拒绝事件、提交 schema 判定 |
| 分析师 | `viewer` | 看板/事件浏览/结果 | 只读查询与导出明细（**不能发起运行，后端返回 403**） |

## 2. 主要功能

- **事件流看板**：流列表、水位线、积压量、按 op 的事件分布、最近运行。
- **事件浏览**：按 op/拒绝标记筛选，按 LSN 序或到达序排列，单事件 before/after 字段级 diff（后端计算）。
- **归并运行**：选 LSN 窗口 → 后端建 run → Celery worker 执行合并 → **整窗 schema gate** → 单事务带 LSN 守卫写入 `dw` 目标表 → 结果落库 → 前端轮询结果。
- **数仓发布**：归并结果真实物理写入目标表（不再只存 `result_json`）。每条目标行带 `_merge_lsn` 位点列，重复投递/迟到旧事件的位点不新于当前值时整行 no-op；同窗口重跑得到唯一结果。
- **整窗阻塞**：任一事件字段与目标表实际列不兼容（缺列/类型不兼容/非空违约）时，状态置为 `blocked`，**整窗不发布、目标表零改动、水位线不推进**，运行详情逐条列出阻塞字段。
- **拒绝与重放**：4 类拒绝原因（`schema_mismatch / pk_missing / parse_error / type_conflict`），按原因做真实载荷修复后重放。
- **schema 演进**：字段级 diff → 兼容等级（`full/backward/forward/breaking`）→ 前滚 SQL / 预检 SQL / 回滚 SQL / 发布步骤。
- **横切**：JWT 三角色 RBAC、审计日志、Redis 滑动窗口限流（`runs` 桶 10 次/分钟）。

## 3. 两个核心算法（Python 真算，前端只展示）

### 算法 1：乱序/重复 CDC 事件去重归并 + 幂等落账

`backend/src/services/merge_engine.py`（纯函数，worker 与 seed 共用）

- 输入：一个 LSN 窗口内的原始事件（到达顺序可能乱序、可能重复）。
- 处理：
  1. 按 `(lsn, received_seq)` 稳定排序；重复键 `(lsn, pk)` 只保留最先到达的一份并计入 `duplicate`；
  2. 带 `reject_reason` 的事件计入 `rejected`，不落账；
  3. 按 LSN 顺序应用 `insert/update/delete`；`delete` 后再 `insert` 视为**重建**（`rebuilt`）；`update` 的 `before` 与当前行不一致时记 `conflict`；
  4. **金额守恒校验**：同 PK 满足 `insert 值 + Σ(after.amount - before.amount) == 最终值`；
  5. **水位线** = 窗口内最小未到达 LSN 的前一个 LSN（有空洞就停在水位线）。
- 输出：`inserted/updated/deleted/rebuilt/upserted/duplicate/rejected/conflicted` 计数、最终行、冲突明细、重复明细、金额校验、`digest`。
- 失败态：主键缺失事件进拒绝队列；未知 op 进拒绝队列；窗口为空/超上限在发起阶段直接 409/413。
- 可复现：事件集合固定 + 稳定排序 → 同一窗口重复运行得到相同 `digest`，结果页标记「幂等」。

### 算法 2：schema 兼容性判定 + 迁移 SQL 生成

`backend/src/services/schema_engine.py`（纯函数）

- 输入：两个 `SchemaVersion` 的字段集合（`name/type/nullable/default/is_pk`）。
- 变更分类（10 类）：`add_nullable / add_required / add_required_with_default / drop_column / type_widen / type_narrow / type_incompatible / nullability_to_required / nullability_to_nullable / pk_change`。
- 兼容口径：**backward** = 新 schema 能读旧数据；**forward** = 旧 schema 能读新数据；**breaking** = 都不成立。汇总取最差；`backward + forward` 混合也判 breaking（方向冲突）。
- 输出：逐条 `compat`、汇总 `compat_level`、受影响列、前滚 SQL（含 `ADD COLUMN ... DEFAULT`、`ALTER COLUMN ... TYPE ... USING`）、预检 SQL、回滚 SQL、发布步骤。
- demo 数据：orders 流 `v1 → v2` = `amount numeric(14,2) → numeric(12,2)`（type_narrow / **breaking**）+ 新增 `channel text`（add_nullable / **backward**），即 1 条 breaking + 1 条 backward。

### 算法 3：整窗 schema gate + 事务化数仓发布

`backend/src/services/target_publisher.py`（worker 与 seed 共用同一条发布链路）

- **schema gate（发布前，无写入）**：读目标表 `information_schema` 的真实物理列，对窗口内**每一条参与归并的事件**逐字段检查——目标表缺列（`unknown_column`）、值与列类型不兼容（`type_incompatible`）、非空列收到 NULL（`not_null_violation`）、insert 缺必填列（`required_missing`）。任一命中即整窗判 `blocked`，返回**全部**阻塞字段（event/lsn/pk/field/原因/期望与实际类型），不执行任何 DML。
- **位点守卫（最新位点为准）**：目标表新增 `_merge_lsn bigint` 列，记录每行最后一次生效事件的 LSN。upsert 走 `INSERT ... ON CONFLICT DO UPDATE ... WHERE _merge_lsn IS NULL OR _merge_lsn < :lsn`，delete 走 `DELETE ... WHERE _merge_lsn <= :lsn`。重复投递与迟到旧事件位点不新于当前值时整行 no-op，当前值不会被回退。
- **整窗原子**：所有 upsert/delete 在同一事务内完成，写入阶段异常整体回滚，目标表不留半批数据；运行记录里的 `target_rows_before / target_rows_after` 与目标表快照均为发布后回读的真实内容。
- **重跑唯一**：同一窗口事件集合固定 → digest 相同；重跑时全部行被守卫跳过，物理表内容、行数、digest 三者保持不变，运行详情标记「幂等」。
- demo 数据：`orders` 流窗口发布到 `dw.orders_dw`（18 行）；`orders_breaking` 流（上游已切含 `channel` 的 v2）发布到停留在旧结构的 `dw.orders_breaking_dw`，整窗被 gate 拦截、目标表保持 0 行。

## 4. 快速启动

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps            # 期望 5 个服务全部 (healthy)
docker compose exec -T backend python -m scripts.seed_demo
```

访问：

| 入口 | 地址 |
|---|---|
| 前端 | http://localhost:18220 |
| 后端 API | http://localhost:19220/api/health |
| 数据库 | localhost:17720（`cdcmerge` / `cdcmerge_pw_2026`） |

`SEED_DEMO=true` 时 backend 启动会自动跑一次幂等 seed；`python -m scripts.seed_demo` 可重复执行，第二次全部 `SEED_SKIPPED`，末尾打印 `SEED_SUMMARY {json}` 供幂等核对。

### 演示账号（密码统一 `Demo@2026`）

| 邮箱 | 角色 | 能做什么 |
|---|---|---|
| `admin@cdc.local` | admin | 全部；建流、改状态、重置水位线 |
| `eng@cdc.local` | engineer | 发起归并、重放拒绝事件、schema 判定 |
| `viewer@cdc.local` | viewer | 只读；发起归并返回 **403** |

## 5. 本地开发

```bash
# 后端
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
alembic upgrade head
uvicorn src.main:app --reload --port 8000

# worker
cd worker && PYTHONPATH=/app:/app/backend celery -A worker_src.config.celery_app worker -B -l info

# 前端
cd frontend && npm install && npm run dev   # /api 代理到 localhost:19220
```

## 6. 技术栈

| 层 | 技术 |
|---|---|
| 前端 | React 18 + TypeScript + Vite + Zustand + react-router；手写 CSS（oklch token + 双字体 `@fontsource`） |
| 后端 | Python 3.11 + FastAPI + SQLAlchemy 2.0 + Alembic + PyJWT + passlib |
| 异步 | Celery 5.4 + Redis 7 |
| 数据库 | PostgreSQL 16（`cdc` schema 平台表 / `dw` schema 目标表） |
| 网关 | Nginx 1.27（`/api/` 反代 + SPA 回落） |
| 容器 | Docker Compose，5 服务全部 healthcheck |

## 7. 目录

```
gb-547/
├── docker-compose.yml / .env.example
├── backend/
│   ├── scripts/seed_demo.py        # 幂等 seed + SEED_SUMMARY
│   ├── src/{config,constants,models,schemas,middlewares,utils,services,controllers,routes,migrations}
│   └── Dockerfile / entrypoint.sh / alembic.ini / requirements.txt
├── worker/
│   ├── src/{config,tasks,core}      # merge_task / heartbeat_task
│   └── Dockerfile / healthcheck.sh
└── frontend/
    ├── src/{api,stores,types,components,hooks,pages,router,utils,constants,styles}
    └── Dockerfile / nginx.conf
```

## 8. 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `COMPOSE_PROJECT_NAME` | `cdcmerge` | 容器名前缀 |
| `FRONTEND_PORT` / `BACKEND_PORT` / `DB_PORT` | `18220` / `19220` / `17720` | 题目分配端口 |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` | `cdcmerge` / `cdcmerge` / `cdcmerge_pw_2026` | PostgreSQL |
| `JWT_SECRET` | `cdcmerge-jwt-secret-change-me-2026` | HS256 密钥 |
| `REDIS_URL` | `redis://redis:6379/0` | broker + backend + 限流 + 心跳 |
| `SEED_DEMO` | `true` | 启动自动 seed |
| `MAX_WINDOW_EVENTS` | `20000` | 单窗口事件上限 |
| `RATE_LIMIT_RUNS_PER_MINUTE` | `10` | 发起归并限流 |

## 9. 共享枚举出现位置（前后端各一份）

| 枚举 | 后端 | 前端 |
|---|---|---|
| Role (`admin/engineer/viewer`) | `backend/src/constants/roles.py` | `frontend/src/constants/roles.ts`、`frontend/src/types/models.ts` |
| CdcOp (`insert/update/delete`) + 中文名 | `backend/src/constants/enums.py` | `frontend/src/constants/cdc.ts` |
| StreamStatus / RunStatus | `backend/src/constants/enums.py` | `frontend/src/constants/cdc.ts` |
| RejectReason / RejectStatus | `backend/src/constants/enums.py` | `frontend/src/constants/cdc.ts` |
| ChangeKind（10 类） | `backend/src/constants/enums.py` | `frontend/src/constants/cdc.ts`、`frontend/src/constants/cdc.ts#CHANGE_KIND_TONE` |
| CompatLevel (`full/backward/forward/breaking`) | `backend/src/constants/enums.py` | `frontend/src/constants/cdc.ts` |
| MergeStrategy (`upsert/append`) | `backend/src/constants/enums.py` | `frontend/src/constants/cdc.ts` |

## 10. Docker 说明

- 5 服务：`frontend`(Nginx) / `backend`(FastAPI) / `worker`(Celery) / `db`(PostgreSQL 16) / `redis`(7)，全部带 healthcheck。
- 依赖顺序：`db`/`redis` healthy → `backend`、`worker`；`backend` healthy → `frontend`。
- worker 的 healthcheck：Redis 心跳键 `cdcmerge:worker:heartbeat`（Celery beat 每 20s 写）兜底 `celery inspect ping`。
- 命名卷 `db_data`、`redis_data`；收尾用 `docker compose down -v --remove-orphans`。

## 11. 已知边界

- 目标表 `dw.orders_dw` / `dw.customers_dw` / `dw.orders_breaking_dw` 由迁移建表，归并结果经 schema gate 后在单事务内真实写入（带 `_merge_lsn` 位点列）；目标表 DDL 仍需人工/迁移维护，发布只按既有物理列做兼容性判定，不自动 ALTER TABLE。
- `delete` 事件在 seed 数据中为 0 条（演示窗口内全为 insert/update），算法的 tombstone/rebuild 与守卫 delete 分支由 `scripts/it_publish_check.py` 的集成用例覆盖。
- 事件来源是数据库表，不是真的 Kafka 消费者。

## License

MIT（演示项目，seed 数据为虚构）。
