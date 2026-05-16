from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.security import decode_access_token
from app.core.session import sessions
from app.core.presence import presence
from app.games.rps.rooms import NUM_ROOMS, rps_room_manager

router = APIRouter(tags=["ws"])


@router.websocket("/ws/rps")
async def rps_ws(websocket: WebSocket, token: str, room: int = 0) -> None:
    await websocket.accept()
    username = decode_access_token(token)
    if username is None or token not in sessions or username == "admindb":
        await websocket.send_json({"type": "room.error", "message": "Unauthorized"})
        await websocket.close()
        return

    if room < 0 or room >= NUM_ROOMS:
        await websocket.send_json({"type": "room.error", "message": "bad_room"})
        await websocket.close()
        return

    err = await rps_room_manager.connect(room, username, websocket)
    if err:
        await websocket.send_json({"type": "room.error", "message": err})
        await websocket.close()
        return

    presence.touch(username, settings.rps_game_key)

    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=0.2)
            except TimeoutError:
                await rps_room_manager.tick_room(room)
                presence.touch(username, settings.rps_game_key)
                continue
            if isinstance(data, dict):
                await rps_room_manager.dispatch_message(room, username, data)
            presence.touch(username, settings.rps_game_key)
    except WebSocketDisconnect:
        await rps_room_manager.disconnect(room, username)
