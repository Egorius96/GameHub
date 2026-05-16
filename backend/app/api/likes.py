from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.gameshub import ensure_gameshub_schema
from app.core.session import sessions
from app.db.models import GameHubUser, GameLike
from app.db.session import get_db
from app.services.ip_detect import get_client_ip
from app.services.ban_state import clear_expired_temp_ban, is_login_blocked


router = APIRouter(prefix="/api/likes", tags=["likes"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return _now().date()


def _session_from_auth(authorization: str) -> tuple[str, Any]:
    token = authorization.replace("Bearer ", "")
    session = sessions.get(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return token, session


class VoteRequest(BaseModel):
    game_key: str = Field(min_length=1, max_length=64)


@router.get("/summary")
def summary(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> dict:
    _, session = _session_from_auth(authorization)
    day = _today()
    # counts
    rows = (
        db.query(GameLike.game_key, func.count(GameLike.id))
        .filter(GameLike.day == day)
        .group_by(GameLike.game_key)
        .all()
    )
    counts = {str(k): int(c) for (k, c) in rows}
    # my vote today
    my = db.query(GameLike).filter(GameLike.user_id == int(session.user.get("id", 0))).filter(GameLike.day == day).first()
    return {"day": str(day), "counts": counts, "my_vote": (my.game_key if my else None)}


@router.post("/vote")
def vote(req: Request, payload: VoteRequest, authorization: str = Header(default=""), db: Session = Depends(get_db)) -> dict:
    token, session = _session_from_auth(authorization)

    # blocked check (session.user is dict from users_api.auth)
    username = str(session.username)
    gh = db.query(GameHubUser).filter(GameHubUser.username == username).first()
    if gh is None:
        raise HTTPException(status_code=400, detail="No active user")
    clear_expired_temp_ban(db, gh)
    db.refresh(gh)
    if is_login_blocked(gh):
        raise HTTPException(status_code=403, detail="Account blocked")

    day = _today()
    ip = get_client_ip(req)

    # only one vote per day (and only one game)
    existing = db.query(GameLike).filter(GameLike.user_id == gh.id).filter(GameLike.day == day).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Already voted today")

    like = GameLike(user_id=gh.id, username=gh.username, game_key=payload.game_key, day=day, ip=ip)
    db.add(like)
    db.commit()

    # mark activity time
    gh.last_active_at = _now()
    gh.login_count = int(getattr(gh, "login_count", 0) or 0)  # no-op but keeps field touched
    db.commit()

    # suspicious marking: если с одного IP за день голосовало слишком много разных аккаунтов — помечаем всех
    # Порог: 4+ аккаунта за день с одного IP.
    distinct_users = (
        db.query(func.count(func.distinct(GameLike.user_id)))
        .filter(GameLike.day == day)
        .filter(GameLike.ip == ip)
        .scalar()
    ) or 0
    if int(distinct_users) >= 4:
        ids = [x[0] for x in db.query(func.distinct(GameLike.user_id)).filter(GameLike.day == day).filter(GameLike.ip == ip).all()]
        db.query(GameHubUser).filter(GameHubUser.id.in_(ids)).update({GameHubUser.suspicious: True}, synchronize_session=False)
        db.commit()

    # return updated counts
    rows = (
        db.query(GameLike.game_key, func.count(GameLike.id))
        .filter(GameLike.day == day)
        .group_by(GameLike.game_key)
        .all()
    )
    counts = {str(k): int(c) for (k, c) in rows}
    return {"ok": True, "day": str(day), "counts": counts, "my_vote": payload.game_key}

