from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.session_resolve import resolve_user_session
from app.core.gameshub import ensure_pro_racing_schema, get_pro_racing_game
from app.core.presence import presence
from app.games.pro_racing.session_manager import session_manager
from app.integrations.users_api import users_api

router = APIRouter(tags=["ws"])


@router.websocket("/ws/game")
async def game_ws(websocket: WebSocket, token: str, mode: str = "normal") -> None:
    await websocket.accept()
    session = resolve_user_session(token)
    if session is None:
        await websocket.send_json({"type": "state.error", "message": "Unauthorized"})
        await websocket.close()
        return

    username = session.username
    presence.touch(username, "misha_pro_racing_game")
    other_data = ensure_pro_racing_schema(session.user.get("other_data", {}) or {})
    game = get_pro_racing_game(other_data)
    car_level = int(game.get("car_level", 1))
    superpowers = game.get("superpowers") if isinstance(game.get("superpowers"), dict) else {}
    key = f"{username}:{id(websocket)}"
    engine = session_manager.create(key, mode, car_level, superpowers=superpowers)

    try:
        while True:
            while True:
                try:
                    event = await asyncio.wait_for(websocket.receive_json(), timeout=0.001)
                    event_type = event.get("type")
                    if event_type == "input.move":
                        player = int(event.get("player", 1))
                        if "dx" in event or "dy" in event:
                            engine.input_move(
                                player,
                                dx=int(event.get("dx", 0)),
                                dy=int(event.get("dy", 0)),
                            )
                        else:
                            engine.input_move(player, str(event.get("direction", "stop")))
                    elif event_type == "input.ability":
                        engine.ability(event.get("ability", ""))
                    elif event_type == "session.restart":
                        engine = session_manager.create(key, mode, car_level, superpowers=superpowers)
                except TimeoutError:
                    break

            state = engine.tick()
            if state["game_over"] and not state.get("persisted"):
                other_data = ensure_pro_racing_schema(session.user.setdefault("other_data", {}) or {})
                game = get_pro_racing_game(other_data)
                other_data["diamonds"] = int(other_data.get("diamonds", 0)) + int(state.get("diamonds_collected", 0))
                game["matches_count"] = int(game.get("matches_count", 0)) + 1
                game["high_score_seconds"] = max(
                    int(game.get("high_score_seconds", 0)),
                    int(state.get("seconds", 0)),
                )
                game["playtime"] = int(game.get("playtime", 0)) + int(state.get("seconds", 0))
                session.user["other_data"] = other_data
                users_api.save_user(session.user)
                engine.state.persisted = True
                state = engine.serialize()
            await websocket.send_json({"type": "state.tick", "payload": state})
            if state["game_over"]:
                await websocket.send_json({"type": "state.game_over", "payload": state})
            await asyncio.sleep(1 / settings.ws_tick_rate)
    except WebSocketDisconnect:
        session_manager.remove(key)
