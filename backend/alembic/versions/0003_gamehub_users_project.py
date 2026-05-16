"""add project to gamehub_users

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-11

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gamehub_users", sa.Column("project", sa.String(length=64), nullable=False, server_default="GamesHub"))
    op.create_index("ix_gamehub_users_project", "gamehub_users", ["project"], unique=False)
    op.alter_column("gamehub_users", "project", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_gamehub_users_project", table_name="gamehub_users")
    op.drop_column("gamehub_users", "project")

