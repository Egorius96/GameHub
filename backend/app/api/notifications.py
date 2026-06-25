"""Глобальные уведомления для авторизованных пользователей GameHub."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from app.core.session import UserSession, sessions
from app.games.team_territory.manager import team_territory_manager
from app.games.team_territory.room_engine import utcnow

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _session(authorization: str = Header(default="")) -> UserSession:
    token = authorization.replace("Bearer ", "")
    sess = sessions.get(token)
    if sess is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return sess


@router.get("/pending")
async def pending_notifications(sess: UserSession = Depends(_session)) -> dict:
    now = utcnow()
    out: list[dict] = []
    async with team_territory_manager.lock:
        for rid, room in team_territory_manager.rooms.items():
            if room.phase != "lobby":
                continue
            if not room.invite_broadcast_until or now >= room.invite_broadcast_until:
                continue
            inviter = room.invite_broadcast_by or ""
            if inviter == sess.username:
                continue
            out.append(
                {
                    "type": "team_territory_invite",
                    "room_id": rid,
                    "inviter": inviter,
                    "expires_at": room.invite_broadcast_until.isoformat(),
                }
            )
    return {"notifications": out}
