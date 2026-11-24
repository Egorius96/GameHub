from __future__ import annotations

import copy
import time

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.gameshub import ensure_gameshub_schema
from app.core.session import sessions
from app.db.models import GameHubUser
from app.db.session import _session_factory
from app.games.pumpkin_dodge.scoring import apply_survival_result, credited_seconds
from app.integrations.users_api import assign_user_other_data

router = APIRouter(prefix="/api/pumpkin-dodge", tags=["pumpkin_dodge"])

# Одна партия на пользователя. Второй /finish без нового /start алмазы не начисляет.
_runs: dict[str, float] = {}


class FinishRequest(BaseModel):
    seconds: int = Field(ge=0, le=6 * 60 * 60)


def _session_from_auth(authorization: str):
    token = authorization.replace("Bearer ", "")
    session = sessions.get(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return session


@router.post("/start")
def start(authorization: str = Header(default="")) -> dict:
    session = _session_from_auth(authorization)
    _runs[str(session.username)] = time.perf_counter()
    return {"ok": True}


@router.post("/finish")
def finish(payload: FinishRequest, authorization: str = Header(default="")) -> dict:
    session = _session_from_auth(authorization)
    username = str(session.username)
    started = _runs.pop(username, None)
    if started is None:
        raise HTTPException(status_code=409, detail="No active run")
    played = credited_seconds(payload.seconds, int(time.perf_counter() - started))
    game_key = settings.pumpkin_dodge_game_key
    db = _session_factory()()
    try:
        user = db.query(GameHubUser).filter(GameHubUser.username == username).with_for_update().first()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        other = ensure_gameshub_schema(copy.deepcopy(user.other_data or {}))
        games = other.setdefault("games", {})
        progress = games.get(game_key)
        if not isinstance(progress, dict):
            progress = {}
        result = apply_survival_result(progress, int(other.get("diamonds") or 0), played)
        games[game_key] = progress
        other["diamonds"] = result["diamonds"]
        assign_user_other_data(user, other)
        db.commit()
    except HTTPException:
        db.rollback()
        _runs.setdefault(username, started)
        raise
    except Exception:
        db.rollback()
        _runs.setdefault(username, started)
        raise HTTPException(status_code=500, detail="Failed to save result")
    finally:
        db.close()

    stored = copy.deepcopy(other)
    for sess in sessions.values():
        if sess.username == username:
            sess.user["other_data"] = copy.deepcopy(stored)
    return result
