from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class LegacyUser(Base):
    """
    Совместимая основа для старого Users API:
      - username/password/project/other_data как в sqlite версии
      - other_data храним в JSONB для быстрых выборок + индексов
    """

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("username", name="uq_users_username"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password: Mapped[str] = mapped_column(Text, nullable=False)
    project: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    other_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
    )


class GameHubUser(Base):
    """
    Пользователи GameHub (отдельно от legacy Users API).
    Храним:
      - username/password для входа
      - other_data JSONB для совместимости с текущей логикой игр
    """

    __tablename__ = "gamehub_users"
    __table_args__ = (UniqueConstraint("username", name="uq_gamehub_users_username"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password: Mapped[str] = mapped_column(Text, nullable=False)
    project: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="GamesHub")
    other_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false", index=True)
    suspicious: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false", index=True)
    login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    banned_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    mod_warning_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
    )


class GameLike(Base):
    __tablename__ = "game_likes"
    __table_args__ = (
        UniqueConstraint("user_id", "day", name="uq_game_likes_user_day"),
        UniqueConstraint("user_id", "game_key", "day", name="uq_game_likes_user_game_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    game_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ip: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())


class IncidentAck(Base):
    """Админ отметил инцидент (ip + день голосов) как обработанный — для счётчика на главной админке."""

    __tablename__ = "incident_ack"

    ip: Mapped[str] = mapped_column(String(64), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    acked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())


class WarningHistory(Base):
    __tablename__ = "warning_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())
    text: Mapped[str] = mapped_column(Text, nullable=False)
    show_until_login_count: Mapped[int] = mapped_column(Integer, nullable=False)


class UserLastIp(Base):
    __tablename__ = "user_last_ip"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("gamehub_users.id", ondelete="CASCADE"), primary_key=True)
    ip: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())


class MessengerFriendship(Base):
    __tablename__ = "messenger_friendship"
    __table_args__ = (
        UniqueConstraint("user_a", "user_b", name="uq_messenger_friendship_pair"),
        CheckConstraint("user_a < user_b", name="ck_messenger_friendship_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_a: Mapped[int] = mapped_column(Integer, ForeignKey("gamehub_users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_b: Mapped[int] = mapped_column(Integer, ForeignKey("gamehub_users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    initiator_id: Mapped[int] = mapped_column(Integer, ForeignKey("gamehub_users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())


class MessengerChat(Base):
    __tablename__ = "messenger_chat"
    __table_args__ = (UniqueConstraint("dm_peer_key", name="uq_messenger_chat_dm_peer_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dm_peer_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    next_seq: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_message_preview: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, server_default=func.now()
    )


class MessengerChatMember(Base):
    __tablename__ = "messenger_chat_member"

    chat_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("messenger_chat.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("gamehub_users.id", ondelete="CASCADE"), primary_key=True, nullable=False, index=True
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_read_seq: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class MessengerMessage(Base):
    __tablename__ = "messenger_message"
    __table_args__ = (UniqueConstraint("chat_id", "seq", name="uq_messenger_message_chat_seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(Integer, ForeignKey("messenger_chat.id", ondelete="CASCADE"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sender_id: Mapped[int] = mapped_column(Integer, ForeignKey("gamehub_users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="text", server_default="text")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GameHubRegistrationLog(Base):
    """Учёт регистраций GameHub по IP и календарному дню (UTC) для лимита."""

    __tablename__ = "gamehub_registration_log"
    __table_args__ = ()

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ip: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("gamehub_users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())


class MessengerDiamondLedger(Base):
    __tablename__ = "messenger_diamond_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now(), index=True)
    from_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("gamehub_users.id", ondelete="CASCADE"), nullable=False, index=True)
    to_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("gamehub_users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    commission: Mapped[int] = mapped_column(Integer, nullable=False)
    total_debit: Mapped[int] = mapped_column(Integer, nullable=False)
    sender_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recipient_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chat_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("messenger_chat.id", ondelete="SET NULL"), nullable=True)
    message_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("messenger_message.id", ondelete="SET NULL"), nullable=True)


