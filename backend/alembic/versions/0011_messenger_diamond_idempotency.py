"""messenger diamond transfer idempotency key

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messenger_diamond_ledger", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.create_index(
        "ix_messenger_diamond_ledger_idempotency_key",
        "messenger_diamond_ledger",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_messenger_diamond_ledger_idempotency_key", table_name="messenger_diamond_ledger")
    op.drop_column("messenger_diamond_ledger", "idempotency_key")
