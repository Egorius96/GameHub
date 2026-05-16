from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import jwt

from app.core.config import settings


def create_access_token(username: str, *, role: str | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=24)
    payload: dict[str, Any] = {"sub": username, "exp": expire}
    if role:
        payload["role"] = role
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
        return payload.get("sub")
    except Exception:
        return None


def decode_access_token_payload(token: str) -> Optional[dict[str, Any]]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None
