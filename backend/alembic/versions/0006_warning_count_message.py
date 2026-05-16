"""warning_count and mod_warning_text on gamehub_users

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-11

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gamehub_users", sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("gamehub_users", sa.Column("mod_warning_text", sa.Text(), nullable=True))
    op.alter_column("gamehub_users", "warning_count", server_default=None)


def downgrade() -> None:
    op.drop_column("gamehub_users", "mod_warning_text")
    op.drop_column("gamehub_users", "warning_count")
