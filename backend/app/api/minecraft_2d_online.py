"""REST Minecraft 2D Online: здоровье, снапшот лобби, подгрузка чанков."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from app.core.config import settings
from app.core.session import UserSession, sessions
from app.games.minecraft_2d_online.manager import minecraft_2d_manager

router = APIRouter(prefix="/api/minecraft-2d-online", tags=["minecraft_2d_online"])


def _session(authorization: str = Header(default="")) -> UserSession:
    token = authorization.replace("Bearer ", "")
    sess = sessions.get(token)
    if sess is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return sess


@router.get("/health")
def health(sess: UserSession = Depends(_session)) -> dict:
    return {"ok": True, "username": sess.username, "game": settings.minecraft_2d_online_game_key}


@router.get("/lobby")
async def lobby_snapshot(_: UserSession = Depends(_session)) -> dict:
    async with minecraft_2d_manager.lock:
        snap = minecraft_2d_manager.snapshot_public()
    snap.pop("self", None)
    return snap


@router.get("/chunks")
async def chunks_near(cx: int, cy: int, r: int = 2, _: UserSession = Depends(_session)) -> dict:
    r = max(0, min(4, r))
    async with minecraft_2d_manager.lock:
        w = minecraft_2d_manager.world
        cs = w.p.chunk_size
        gx = cx * cs + cs // 2
        gy = cy * cs + cs // 2
        tiles = w.snapshot_chunk_keys_near(gx, gy, radius_chunks=r)
        return {"chunk_size": cs, "cx": cx, "cy": cy, "r": r, "chunks": tiles}
