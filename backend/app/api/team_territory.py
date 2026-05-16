"""REST Team Territory: комнаты и вспомогательные запросы."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.session import UserSession, sessions
from app.games.team_territory.manager import team_territory_manager
from app.games.team_territory.room_engine import utcnow
from app.games.team_territory.teams import team_count_bounds

router = APIRouter(prefix="/api/team-territory", tags=["team_territory"])


def _session(authorization: str = Header(default="")) -> UserSession:
    token = authorization.replace("Bearer ", "")
    sess = sessions.get(token)
    if sess is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return sess


@router.get("/health")
def health(sess: UserSession = Depends(_session)) -> dict:
    return {"ok": True, "username": sess.username}


@router.get("/rooms")
async def list_rooms(_: UserSession = Depends(_session)) -> dict:
    async with team_territory_manager.lock:
        out = []
        for rid, room in team_territory_manager.rooms.items():
            out.append(
                {
                    "room_id": rid,
                    "phase": room.phase,
                    "num_teams": room.num_teams,
                    "players": len(room.players),
                }
            )
    return {"rooms": out}


class CreateRoomBody(BaseModel):
    room_id: str = Field(default="default", min_length=1, max_length=64)
    num_teams: int = Field(default=2, ge=2, le=4)


@router.post("/rooms")
async def create_room(body: CreateRoomBody, _: UserSession = Depends(_session)) -> dict:
    lo, hi = team_count_bounds()
    nt = max(lo, min(hi, int(body.num_teams)))
    async with team_territory_manager.lock:
        room = team_territory_manager.get_or_create_room(body.room_id.strip(), nt)
        if room.phase != "lobby":
            raise HTTPException(status_code=400, detail="room_not_lobby")
        room.num_teams = nt
    return {"room_id": room.room_id, "num_teams": room.num_teams}


@router.get("/rooms/{room_id}/snapshot")
async def room_snapshot(room_id: str, sess: UserSession = Depends(_session)) -> dict:
    async with team_territory_manager.lock:
        room = team_territory_manager.rooms.get(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="not_found")
        from app.games.team_territory.room_engine import opponent_ink_snapshot

        snap = room.snapshot(sess.username, utcnow(), lambda v: opponent_ink_snapshot(room, v))
    return snap
