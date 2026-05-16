from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.presence import presence
from app.core.session import sessions

router = APIRouter(prefix="/api/presence", tags=["presence"])


class PresencePingRequest(BaseModel):
    game: str | None = Field(default=None, min_length=1, max_length=64)
    source: str | None = Field(default=None, min_length=1, max_length=64)


def _session_from_auth(authorization: str):
    token = authorization.replace("Bearer ", "")
    session = sessions.get(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return session


@router.post("/ping")
def ping(payload: PresencePingRequest, authorization: str = Header(default="")) -> dict:
    session = _session_from_auth(authorization)
    presence.touch(session.username, payload.game)
    return {"ok": True}


@router.get("/summary")
def summary(authorization: str = Header(default="")) -> dict:
    session = _session_from_auth(authorization)
    presence.touch(session.username, None)
    return presence.snapshot(online_seconds=60)

