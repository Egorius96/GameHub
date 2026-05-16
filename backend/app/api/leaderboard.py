from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query

from app.core.session import sessions
from app.core.config import settings
from app.core.gameshub import ensure_gameshub_schema, ensure_pro_racing_schema
from app.integrations.users_api import users_api

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])


@router.get("")
def leaderboard(limit: int = Query(default=10, ge=1, le=50), authorization: str = Header(default="")) -> dict:
    token = authorization.replace("Bearer ", "")
    session = sessions.get(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = users_api.get_users_by_project(session.username, session.password)
    users = data.get("users", [])
    # системного пользователя каталога не показываем в лидерборде
    users = [u for u in users if u.get("username") != settings.catalog_username]
    def score(u: dict) -> int:
        other = ensure_pro_racing_schema(u.get("other_data") or {})
        games = other.get("games") or {}
        game = games.get("misha_pro_racing_game") or {}
        return int(game.get("high_score_seconds", 0))

    users.sort(key=score, reverse=True)
    for u in users:
        u["other_data"] = ensure_gameshub_schema(u.get("other_data") or {})
    top_users = users[:limit]
    if not any(user.get("username") == session.username for user in top_users):
        current = next((user for user in users if user.get("username") == session.username), None)
        if current is None:
            current = session.user
        if len(top_users) >= limit:
            top_users = top_users[:-1] + [current]
        else:
            top_users.append(current)
    return {"users": top_users}
