from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query

from app.core.config import settings
from app.core.gameshub import ensure_gameshub_schema, ensure_pro_racing_schema
from app.core.session import sessions
from app.games.pumpkin_dodge.scoring import high_score_of, pick_leaderboard
from app.integrations.users_api import users_api

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])

_SCORE_GAMES = frozenset({settings.pro_racing_game_key, settings.pumpkin_dodge_game_key})


def _score(user: dict, game_key: str) -> int:
    raw = user.get("other_data") or {}
    if game_key == settings.pro_racing_game_key:
        other = ensure_pro_racing_schema(raw)
    else:
        other = raw if isinstance(raw, dict) else {}
    return high_score_of(other, game_key)


@router.get("")
def leaderboard(
    limit: int = Query(default=10, ge=1, le=50),
    game: str = Query(default=""),
    authorization: str = Header(default=""),
) -> dict:
    token = authorization.replace("Bearer ", "")
    session = sessions.get(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    game_key = game or settings.pro_racing_game_key
    if game_key not in _SCORE_GAMES:
        raise HTTPException(status_code=400, detail="Unknown game")

    data = users_api.get_users_by_project(session.username, session.password)
    users = [u for u in data.get("users", []) if u.get("username") != settings.catalog_username]
    for user in users:
        user["other_data"] = ensure_gameshub_schema(user.get("other_data") or {})
    top_users = pick_leaderboard(
        users,
        lambda user: _score(user, game_key),
        session.username,
        limit,
        session.user,
    )
    return {"users": top_users}
