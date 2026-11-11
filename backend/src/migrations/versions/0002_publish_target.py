"""窗口归并真实落库：目标表加 _merge_lsn 位点列，merge_runs 加发布追踪列。

Revision ID: 0002_publish_target
Revises: 0001_initial
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from src.config.settings import settings

revision = "0002_publish_target"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

CDC = settings.cdc_schema
DW = settings.target_schema
MERGE_LSN = "_merge_lsn"


def _column_exists(bind, schema: str, table: str, column: str) -> bool:
    row = bind.execute(
        sa.text(
            """
            SELECT 1 FROM information_schema.columns
             WHERE table_schema = :schema AND table_name = :table AND column_name = :column
            """
        ),
        {"schema": schema, "table": table, "column": column},
    ).first()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()

    # 演示「整窗阻塞」的目标表：停留在旧版结构（无 channel 列），等上游 v2 事件撞 gate
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {DW}.orders_breaking_dw (
            order_id      text          NOT NULL PRIMARY KEY,
            member_id     text,
            amount        numeric(14,2),
            qty           integer,
            status        text,
            updated_at    timestamp,
            {MERGE_LSN}   bigint
        )
        """
    )

    # 目标表位点列：记录每行最后被哪个 LSN 的事件更新，是 LSN 守卫幂等的基础
    for table in ("orders_dw", "customers_dw"):
        if not _column_exists(bind, DW, table, MERGE_LSN):
            op.execute(
                f"ALTER TABLE {DW}.{table} ADD COLUMN {MERGE_LSN} bigint"
            )
            op.execute(
                f"COMMENT ON COLUMN {DW}.{table}.{MERGE_LSN} IS '归并位点：该行最后一次生效事件的 LSN'"
            )

    # 0001 通过 Base.metadata.create_all 建表，全新库的 merge_runs 已带最新模型列（JSONB）；
    # 因此这里全部按 information_schema 做存在性判断，保证全新安装与升级安装都幂等。
    run_columns = {
        "published": sa.Boolean(),
        "publish_json": postgresql.JSONB(),
        "target_rows_before": sa.Integer(),
        "target_rows_after": sa.Integer(),
    }
    for column, column_type in run_columns.items():
        if not _column_exists(bind, CDC, "merge_runs", column):
            op.add_column(
                "merge_runs",
                sa.Column(column, column_type, nullable=True),
                schema=CDC,
            )

    # create_all 会按自己的命名约定（带 schema 前缀）先建索引，这里只认“该列已有索引”
    index_exists = bind.execute(
        sa.text(
            """
            SELECT 1 FROM pg_indexes
             WHERE schemaname = :schema AND tablename = 'merge_runs'
               AND indexdef ILIKE '%(published)%'
            """
        ),
        {"schema": CDC},
    ).first()
    if index_exists is None:
        op.create_index(
            "ix_merge_runs_published",
            "merge_runs",
            ["published"],
            schema=CDC,
        )


def downgrade() -> None:
    op.drop_index("ix_merge_runs_published", table_name="merge_runs", schema=CDC)
    op.drop_column("merge_runs", "target_rows_after", schema=CDC)
    op.drop_column("merge_runs", "target_rows_before", schema=CDC)
    op.drop_column("merge_runs", "publish_json", schema=CDC)
    op.drop_column("merge_runs", "published", schema=CDC)
    op.execute(f"DROP TABLE IF EXISTS {DW}.orders_breaking_dw")
    for table in ("orders_dw", "customers_dw"):
        op.execute(f"ALTER TABLE {DW}.{table} DROP COLUMN IF EXISTS {MERGE_LSN}")
