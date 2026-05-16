"""request stats tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-11

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "request_stats_daily",
        sa.Column("day", sa.Date(), primary_key=True, nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_table(
        "request_stats_path",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("method", sa.String(length=12), nullable=False),
        sa.Column("path", sa.String(length=256), nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("day", "method", "path", name="pk_request_stats_path"),
    )
    op.create_index("ix_request_stats_path_day", "request_stats_path", ["day"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_request_stats_path_day", table_name="request_stats_path")
    op.drop_table("request_stats_path")
    op.drop_table("request_stats_daily")

