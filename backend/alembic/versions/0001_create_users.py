"""create users table

Revision ID: 0001
Revises: 
Create Date: 2026-05-11

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password", sa.Text(), nullable=False),
        sa.Column("project", sa.String(length=64), nullable=False),
        sa.Column("other_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_project", "users", ["project"], unique=False)
    # Универсальный индекс по JSON для точечных фильтров/поиска ключей (минимальная нагрузка на запись).
    op.create_index("ix_users_other_data_gin", "users", ["other_data"], unique=False, postgresql_using="gin")

    # Индекс под leaderboard (Pro Racing): сортировка по high_score_seconds в other_data JSON.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_users_pr_high_score
        ON users (
          ((other_data->'games'->'misha_pro_racing_game'->>'high_score_seconds')::int)
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_pr_high_score;")
    op.drop_index("ix_users_other_data_gin", table_name="users")
    op.drop_index("ix_users_project", table_name="users")
    op.drop_table("users")

