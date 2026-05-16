"""likes and moderation tables/columns

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-11

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # gamehub_users columns
    op.add_column("gamehub_users", sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("gamehub_users", sa.Column("suspicious", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("gamehub_users", sa.Column("login_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("gamehub_users", sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_gamehub_users_blocked", "gamehub_users", ["blocked"], unique=False)
    op.create_index("ix_gamehub_users_suspicious", "gamehub_users", ["suspicious"], unique=False)

    # game_likes
    op.create_table(
        "game_likes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("game_key", sa.String(length=64), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "day", name="uq_game_likes_user_day"),
        sa.UniqueConstraint("user_id", "game_key", "day", name="uq_game_likes_user_game_day"),
    )
    op.create_index("ix_game_likes_day_game", "game_likes", ["day", "game_key"], unique=False)
    op.create_index("ix_game_likes_ip_day", "game_likes", ["ip", "day"], unique=False)
    op.create_index("ix_game_likes_user_id", "game_likes", ["user_id"], unique=False)

    # warning history
    op.create_table(
        "warning_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("show_until_login_count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_warning_history_user_id", "warning_history", ["user_id"], unique=False)

    # cleanup server_defaults for new columns
    op.alter_column("gamehub_users", "blocked", server_default=None)
    op.alter_column("gamehub_users", "suspicious", server_default=None)
    op.alter_column("gamehub_users", "login_count", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_warning_history_user_id", table_name="warning_history")
    op.drop_table("warning_history")

    op.drop_index("ix_game_likes_user_id", table_name="game_likes")
    op.drop_index("ix_game_likes_ip_day", table_name="game_likes")
    op.drop_index("ix_game_likes_day_game", table_name="game_likes")
    op.drop_table("game_likes")

    op.drop_index("ix_gamehub_users_suspicious", table_name="gamehub_users")
    op.drop_index("ix_gamehub_users_blocked", table_name="gamehub_users")
    op.drop_column("gamehub_users", "last_active_at")
    op.drop_column("gamehub_users", "login_count")
    op.drop_column("gamehub_users", "suspicious")
    op.drop_column("gamehub_users", "blocked")

