"""banned_until for temporary bans

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-11

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gamehub_users", sa.Column("banned_until", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_gamehub_users_banned_until", "gamehub_users", ["banned_until"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_gamehub_users_banned_until", table_name="gamehub_users")
    op.drop_column("gamehub_users", "banned_until")
