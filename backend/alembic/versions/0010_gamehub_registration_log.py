"""gamehub_registration_log: daily registration limit per IP

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-11

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gamehub_registration_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["gamehub_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gamehub_registration_log_ip_day", "gamehub_registration_log", ["ip", "day"])


def downgrade() -> None:
    op.drop_table("gamehub_registration_log")
