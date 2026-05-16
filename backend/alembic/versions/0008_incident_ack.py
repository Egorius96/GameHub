"""incident_ack for admin incident review tracking

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-11

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incident_ack",
        sa.Column("ip", sa.String(length=64), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("ip", "day", name="pk_incident_ack"),
    )


def downgrade() -> None:
    op.drop_table("incident_ack")
