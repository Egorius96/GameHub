"""WebSocket Team Territory: состояние матча и действия."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.security import decode_access_token
from app.core.session import sessions
from app.core.presence import presence
from app.games.team_territory.constants import tt_params
from app.games.team_territory.manager import team_territory_manager
from app.games.team_territory.room_engine import utcnow
from app.integrations.users_api import users_api

router = APIRouter(tags=["ws"])


async def _apply_buy_paint(room_id: str, username: str) -> dict:
    p = tt_params()
    async with team_territory_manager.lock:
        room = team_territory_manager.rooms.get(room_id)
        if not room or room.phase != "playing":
            return {"ok": False, "error": "not_playing"}
        pl = room.players.get(username)
        if not pl or pl.role != "player":
            return {"ok": False, "error": "not_player"}
        if pl.buys_in_match >= p.max_buys_per_match:
            return {"ok": False, "error": "max_buys"}
        if pl.paint >= p.paint_max:
            return {"ok": False, "error": "paint_full"}
        cost = p.diamond_cost
        bundle = p.bundle
        new_paint = min(p.paint_max, pl.paint + bundle)
        pl.buys_in_match += 1
        pl.paint = new_paint
        room.touch_activity(utcnow(), team_id=pl.team_id)
    bal = users_api.adjust_diamonds(username, -cost)
    if bal is None:
        async with team_territory_manager.lock:
            r2 = team_territory_manager.rooms.get(room_id)
            if r2 and username in r2.players:
                pl2 = r2.players[username]
                pl2.buys_in_match = max(0, pl2.buys_in_match - 1)
                pl2.paint = max(0, pl2.paint - bundle)
        return {"ok": False, "error": "not_enough_diamonds"}
    return {"ok": True, "paint": new_paint, "diamonds": bal}


@router.websocket("/ws/team-territory")
async def team_territory_ws(websocket: WebSocket, token: str, room_id: str = "default") -> None:
    await websocket.accept()
    username = decode_access_token(token)
    if username is None or token not in sessions or username == "admindb":
        await websocket.send_json({"type": "error", "message": "Unauthorized"})
        await websocket.close()
        return

    rid = (room_id or "default").strip()[:64] or "default"
    await team_territory_manager.register_ws(rid, username, websocket)
    presence.touch(username, settings.team_territory_game_key)
    await team_territory_manager.broadcast_room(rid)

    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=0.35)
            except TimeoutError:
                await team_territory_manager.broadcast_room(rid)
                presence.touch(username, settings.team_territory_game_key)
                continue
            if not isinstance(data, dict):
                continue
            extra = await team_territory_manager.handle_client_message(rid, username, data)
            if isinstance(extra, dict) and extra.get("defer") == "buy_paint":
                out = await _apply_buy_paint(rid, username)
                await websocket.send_json({"type": "buy_paint_result", "payload": out})
            elif isinstance(extra, dict) and extra.get("error"):
                await websocket.send_json({"type": "error", "message": extra["error"]})
            elif isinstance(extra, dict) and extra.get("challenge_result") is not None:
                await websocket.send_json({"type": "challenge_result", "payload": extra["challenge_result"]})
            await team_territory_manager.broadcast_room(rid)
            presence.touch(username, settings.team_territory_game_key)
    except WebSocketDisconnect:
        await team_territory_manager.unregister_ws(rid, username)
