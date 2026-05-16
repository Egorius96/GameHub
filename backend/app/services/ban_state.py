from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import GameHubUser


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def clear_expired_temp_ban(db: Session, u: GameHubUser, now: datetime | None = None) -> None:
    """Снять истёкший временный бан (blocked + banned_until в прошлом)."""
    now = now or utcnow()
    if not u.blocked:
        return
    bu = getattr(u, "banned_until", None)
    if bu is not None and bu <= now:
        u.blocked = False
        u.banned_until = None
        db.commit()


def is_login_blocked(u: GameHubUser, now: datetime | None = None) -> bool:
    """Нельзя входить: перманентный бан или активный временный."""
    now = now or utcnow()
    if not u.blocked:
        return False
    bu = getattr(u, "banned_until", None)
    if bu is None:
        return True
    return bu > now


def temp_ban_remaining_seconds(u: GameHubUser, now: datetime | None = None) -> int:
    now = now or utcnow()
    bu = getattr(u, "banned_until", None)
    if bu is None or bu <= now:
        return 0
    return max(0, int((bu - now).total_seconds()))
