from __future__ import annotations

from app.core.gameshub import ensure_gameshub_schema
from app.core.reserved_usernames import is_system_service_username
from app.core.security import decode_access_token
from app.core.session import UserSession, sessions
from app.db.models import GameHubUser
from app.db.session import _session_factory
from app.integrations.users_api import users_api


def resolve_user_session(token: str) -> UserSession | None:
    """Вернуть сессию по токену; при валидном JWT восстановить из БД после рестарта бэкенда."""
    existing = sessions.get(token)
    if existing is not None:
        return existing

    username = decode_access_token(token)
    if not username or is_system_service_username(username):
        return None

    db = _session_factory()()
    try:
        gh = db.query(GameHubUser).filter(GameHubUser.username == username).first()
        if gh is None:
            return None
        user = users_api.auth(username, gh.password)
        if user.get("error") or not user.get("username"):
            return None
        other = ensure_gameshub_schema(user.get("other_data") or {})
        user["other_data"] = other
        sess = UserSession(username=username, password=gh.password, user=user)
        sessions[token] = sess
        return sess
    finally:
        db.close()
