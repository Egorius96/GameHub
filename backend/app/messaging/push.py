from __future__ import annotations

import asyncio
from typing import Any

from starlette.websockets import WebSocket

_lock = asyncio.Lock()
_by_user: dict[int, list[WebSocket]] = {}


async def register(user_id: int, ws: WebSocket) -> None:
    async with _lock:
        _by_user.setdefault(user_id, []).append(ws)


async def unregister(user_id: int, ws: WebSocket) -> None:
    async with _lock:
        lst = _by_user.get(user_id)
        if not lst:
            return
        try:
            lst.remove(ws)
        except ValueError:
            return
        if not lst:
            _by_user.pop(user_id, None)


async def push_to_users(user_ids: list[int], payload: dict[str, Any]) -> None:
    async with _lock:
        targets: list[WebSocket] = []
        for uid in user_ids:
            targets.extend(list(_by_user.get(uid, [])))
    for ws in targets:
        try:
            await ws.send_json(payload)
        except Exception:
            continue
