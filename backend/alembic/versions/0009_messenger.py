"""messenger tables + user_last_ip

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-11

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_last_ip",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["gamehub_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "messenger_friendship",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_a", sa.Integer(), nullable=False),
        sa.Column("user_b", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("initiator_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("user_a < user_b", name="ck_messenger_friendship_order"),
        sa.ForeignKeyConstraint(["user_a"], ["gamehub_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_b"], ["gamehub_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["initiator_id"], ["gamehub_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_a", "user_b", name="uq_messenger_friendship_pair"),
    )
    op.create_index("ix_messenger_friendship_user_a", "messenger_friendship", ["user_a"])
    op.create_index("ix_messenger_friendship_user_b", "messenger_friendship", ["user_b"])

    op.create_table(
        "messenger_chat",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("type", sa.String(length=8), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=True),
        sa.Column("dm_peer_key", sa.String(length=32), nullable=True),
        sa.Column("next_seq", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_preview", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dm_peer_key", name="uq_messenger_chat_dm_peer_key"),
    )
    op.create_index("ix_messenger_chat_type", "messenger_chat", ["type"])
    op.create_index("ix_messenger_chat_last_message_at", "messenger_chat", ["last_message_at"])

    op.create_table(
        "messenger_chat_member",
        sa.Column("chat_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_read_seq", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("unread_count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["chat_id"], ["messenger_chat.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["gamehub_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chat_id", "user_id"),
    )
    op.create_index("ix_messenger_chat_member_user_id", "messenger_chat_member", ["user_id"])

    op.create_table(
        "messenger_message",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="text"),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["chat_id"], ["messenger_chat.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["gamehub_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "seq", name="uq_messenger_message_chat_seq"),
    )
    op.create_index("ix_messenger_message_chat_id_seq", "messenger_message", ["chat_id", "seq"])
    op.create_index("ix_messenger_message_sender_id", "messenger_message", ["sender_id"])

    op.create_table(
        "messenger_diamond_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("from_user_id", sa.Integer(), nullable=False),
        sa.Column("to_user_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("commission", sa.Integer(), nullable=False),
        sa.Column("total_debit", sa.Integer(), nullable=False),
        sa.Column("sender_ip", sa.String(length=64), nullable=True),
        sa.Column("recipient_ip", sa.String(length=64), nullable=True),
        sa.Column("chat_id", sa.Integer(), nullable=True),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["from_user_id"], ["gamehub_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_user_id"], ["gamehub_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chat_id"], ["messenger_chat.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["message_id"], ["messenger_message.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messenger_diamond_ledger_created_at", "messenger_diamond_ledger", ["created_at"])
    op.create_index("ix_messenger_diamond_ledger_from", "messenger_diamond_ledger", ["from_user_id"])
    op.create_index("ix_messenger_diamond_ledger_to", "messenger_diamond_ledger", ["to_user_id"])


def downgrade() -> None:
    op.drop_table("messenger_diamond_ledger")
    op.drop_table("messenger_message")
    op.drop_table("messenger_chat_member")
    op.drop_table("messenger_chat")
    op.drop_table("messenger_friendship")
    op.drop_table("user_last_ip")
