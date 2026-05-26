"""Зарезервированные имена — нельзя регистрировать как обычный аккаунт GameHub."""

from __future__ import annotations

RESERVED_USERNAMES: frozenset[str] = frozenset({"admindb", "database"})

SYSTEM_SERVICE_USERNAMES: frozenset[str] = frozenset({"admindb", "database"})


def is_reserved_username(username: str) -> bool:
    return username.strip().lower() in RESERVED_USERNAMES


def is_system_service_username(username: str | None) -> bool:
    if not username:
        return False
    return username.strip().lower() in SYSTEM_SERVICE_USERNAMES
