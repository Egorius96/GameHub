"""WebSocket Minecraft 2D Online."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.security import decode_access_token
from app.core.session import sessions
from app.core.presence import presence
from app.games.minecraft_2d_online.manager import minecraft_2d_manager

router = APIRouter(tags=["ws"])


@router.websocket("/ws/minecraft-2d-online")
async def minecraft_2d_ws(websocket: WebSocket, token: str) -> None:
    await websocket.accept()
    username = decode_access_token(token)
    if username is None or token not in sessions or username == "admindb":
        await websocket.send_json({"type": "error", "message": "Unauthorized"})
        await websocket.close()
        return

    snap0 = await minecraft_2d_manager.register_ws(username, websocket)
    await websocket.send_json(snap0)
    presence.touch(username, settings.minecraft_2d_online_game_key)
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=0.4)
            except TimeoutError:
                await websocket.send_json(await minecraft_2d_manager.snapshot_for(username))
                presence.touch(username, settings.minecraft_2d_online_game_key)
                continue
            if not isinstance(data, dict):
                continue
            extra = await minecraft_2d_manager.handle_message(username, data)
            if isinstance(extra, dict) and extra.get("error"):
                await websocket.send_json({"type": "action_result", "ok": False, "error": extra["error"]})
            elif isinstance(extra, dict) and extra.get("ok") is not None:
                await websocket.send_json({"type": "action_result", "payload": extra})
            await websocket.send_json(await minecraft_2d_manager.snapshot_for(username))
            presence.touch(username, settings.minecraft_2d_online_game_key)
    except WebSocketDisconnect:
        await minecraft_2d_manager.unregister_ws(username)
