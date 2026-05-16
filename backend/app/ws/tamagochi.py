from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.security import decode_access_token
from app.core.session import sessions
from app.core.gameshub import ensure_gameshub_schema
from app.core.presence import presence
from app.games.tamagochi_world.pet_state import merge_shop_toy_buffs_from_progress
from app.games.tamagochi_world.world import tamagochi_world
from app.integrations.users_api import users_api


router = APIRouter(tags=["ws"])

_world_loop_task: asyncio.Task[None] | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ws_tick_interval_sec() -> float:
    return 1 / max(5, min(settings.ws_tick_rate, 20))


async def tamagochi_world_background_loop() -> None:
    """Единственный поток симуляции мира; WS только читает snapshot."""
    interval = _ws_tick_interval_sec()
    while True:
        await asyncio.sleep(interval)
        now = _now()
        if not tamagochi_world.any_clients_connected():
            continue
        tamagochi_world.run_simulation_step(now=now)


def start_tamagochi_world_background_loop() -> None:
    global _world_loop_task
    if _world_loop_task is not None and not _world_loop_task.done():
        return
    _world_loop_task = asyncio.create_task(
        tamagochi_world_background_loop(),
        name="tamagochi_world_background_loop",
    )


async def stop_tamagochi_world_background_loop() -> None:
    global _world_loop_task
    if _world_loop_task is None or _world_loop_task.done():
        _world_loop_task = None
        return
    _world_loop_task.cancel()
    try:
        await _world_loop_task
    except asyncio.CancelledError:
        pass
    _world_loop_task = None


@router.websocket("/ws/tamagochi")
async def tamagochi_ws(websocket: WebSocket, token: str) -> None:
    await websocket.accept()
    username = decode_access_token(token)
    if username is None or token not in sessions:
        await websocket.send_json({"type": "state.error", "message": "Unauthorized"})
        await websocket.close()
        return

    session = sessions[token]
    presence.touch(username, settings.tamagochi_game_key)
    other = ensure_gameshub_schema(session.user.get("other_data") or {})
    session.user["other_data"] = other
    games = other.get("games") or {}
    progress = games.get(settings.tamagochi_game_key) if isinstance(games, dict) else None
    if not isinstance(progress, dict):
        progress = {"playtime": 0, "pet_state": None, "neglect": {}}
        if isinstance(games, dict):
            games[settings.tamagochi_game_key] = progress

    pet = progress.get("pet_state") if isinstance(progress, dict) else None
    neglect = progress.get("neglect") if isinstance(progress, dict) else None
    if isinstance(pet, dict) and isinstance(progress, dict):
        merge_shop_toy_buffs_from_progress(progress, pet)
    now = _now()
    if not tamagochi_world.connect_owner(
        username,
        pet if isinstance(pet, dict) else None,
        neglect if isinstance(neglect, dict) else None,
        now=now,
    ):
        await websocket.send_json(
            {
                "type": "state.error",
                "message": "На поле уже играет слишком много игроков (максимум 10). Подождите, пока число игроков онлайн уменьшится.",
            }
        )
        await websocket.close()
        return

    persist_every = 10.0
    last_persist_at = now

    try:
        while True:
            while True:
                try:
                    _ = await asyncio.wait_for(websocket.receive_json(), timeout=0.001)
                except TimeoutError:
                    break

            now = _now()
            presence.touch(username, settings.tamagochi_game_key)

            payload = tamagochi_world.snapshot_locked(now=now, me=username)

            if (now - last_persist_at).total_seconds() >= persist_every:
                me_pet = (payload.get("me") or {}).get("pet")
                me_neglect = (payload.get("me") or {}).get("neglect")
                if isinstance(me_pet, dict) and isinstance(progress, dict):
                    progress["pet_state"] = me_pet
                    if isinstance(me_neglect, dict):
                        progress["neglect"] = me_neglect
                    progress["last_update_at"] = me_pet.get("last_update_at")
                    session.user["other_data"] = other
                    users_api.save_user(session.user)
                last_persist_at = now

            await websocket.send_json({"type": "state.tick", "payload": payload})
            await asyncio.sleep(_ws_tick_interval_sec())
    except WebSocketDisconnect:
        tamagochi_world.disconnect_owner(username)
        now = _now()
        games_local = other.get("games") if isinstance(other.get("games"), dict) else {}
        progress_local = games_local.get(settings.tamagochi_game_key)
        if isinstance(progress_local, dict):
            payload = tamagochi_world.snapshot_locked(now=now, me=username)
            me_pet = (payload.get("me") or {}).get("pet")
            me_neglect = (payload.get("me") or {}).get("neglect")
            if isinstance(me_pet, dict):
                progress_local["pet_state"] = me_pet
                if isinstance(me_neglect, dict):
                    progress_local["neglect"] = me_neglect
                progress_local["last_update_at"] = me_pet.get("last_update_at")
                session.user["other_data"] = other
                users_api.save_user(session.user)
