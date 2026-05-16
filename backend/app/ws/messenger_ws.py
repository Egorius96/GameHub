from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.presence import presence
from app.core.security import decode_access_token
from app.core.session import sessions
from app.db.models import GameHubUser
from app.db.session import _session_factory
from app.messaging.push import register, unregister

router = APIRouter(tags=["ws"])


@router.websocket("/ws/messenger")
async def messenger_ws(websocket: WebSocket, token: str) -> None:
    await websocket.accept()
    username = decode_access_token(token)
    if username is None or token not in sessions or username == "admindb":
        await websocket.send_json({"type": "error", "message": "Unauthorized"})
        await websocket.close()
        return

    db = _session_factory()()
    try:
        u = db.query(GameHubUser).filter(GameHubUser.username == username).first()
        if u is None:
            await websocket.send_json({"type": "error", "message": "Unauthorized"})
            await websocket.close()
            return
        user_id = int(u.id)
    finally:
        db.close()

    presence.touch(username, "messenger")
    await register(user_id, websocket)
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
            except TimeoutError:
                presence.touch(username, "messenger")
                continue
    except WebSocketDisconnect:
        pass
    finally:
        await unregister(user_id, websocket)
