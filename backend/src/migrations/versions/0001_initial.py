"""初始化 cdc 平台表与 dw 目标表。

Revision ID: 0001_initial
"""
from __future__ import annotations

from alembic import op

from src.config.settings import settings
from src.models import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

CDC = settings.cdc_schema
DW = settings.target_schema

DW_DDL = f"""
CREATE TABLE IF NOT EXISTS {DW}.orders_dw (
    order_id      text          NOT NULL PRIMARY KEY,
    member_id     text,
    amount        numeric(14,2),
    qty           integer,
    status        text,
    updated_at    timestamp
);

CREATE TABLE IF NOT EXISTS {DW}.customers_dw (
    customer_id   text          NOT NULL PRIMARY KEY,
    mobile        text,
    tier          text,
    city          text,
    updated_at    timestamp
);
"""


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {CDC}")
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {DW}")
    Base.metadata.create_all(bind=bind)
    op.execute(DW_DDL)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
    op.execute(f"DROP SCHEMA IF EXISTS {DW} CASCADE")
    op.execute(f"DROP SCHEMA IF EXISTS {CDC} CASCADE")
