"""In-memory комнаты Team Territory + рассылка WS."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from app.core.config import settings
from app.games.team_territory.challenge import load_spelling_words
from app.games.team_territory.room_engine import (
    TerritoryRoom,
    add_player,
    handle_challenge_answer,
    opponent_ink_snapshot,
    start_challenge_if_allowed,
    utcnow,
)
from app.games.team_territory.teams import team_count_bounds


@dataclass
class TeamTerritoryManager:
    rooms: dict[str, TerritoryRoom] = field(default_factory=dict)
    connections: dict[str, dict[str, WebSocket]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    spelling_words: list[str] = field(default_factory=list)
    _reward_granted: set[str] = field(default_factory=set)  # match_id:username in-memory guard

    def ensure_spelling_words(self) -> None:
        if not self.spelling_words:
            from app.games.team_territory.constants import tt_params

            self.spelling_words = load_spelling_words(tt_params())

    def get_or_create_room(self, room_id: str, num_teams: int = 2) -> TerritoryRoom:
        lo, hi = team_count_bounds()
        nt = max(lo, min(hi, int(num_teams)))
        if room_id not in self.rooms:
            self.rooms[room_id] = TerritoryRoom(room_id=room_id, num_teams=nt)
        r = self.rooms[room_id]
        if r.num_teams != nt and r.phase == "lobby" and not r.players:
            r.num_teams = nt
        return r

    async def register_ws(self, room_id: str, username: str, ws: WebSocket) -> TerritoryRoom:
        async with self.lock:
            room = self.get_or_create_room(room_id)
            if room.phase == "playing" and username not in room.players:
                add_player(room, username, role="spectator", now=utcnow())
                if username not in room.spectator_queue_next:
                    room.spectator_queue_next.append(username)
            elif username not in room.players:
                add_player(room, username, role="player", now=utcnow())
            else:
                room.players[username].connected = True
            self.connections.setdefault(room_id, {})[username] = ws
            return room

    async def unregister_ws(self, room_id: str, username: str) -> None:
        async with self.lock:
            con = self.connections.get(room_id)
            if con and con.get(username) is not None:
                del con[username]
            room = self.rooms.get(room_id)
            if room and username in room.players:
                room.players[username].connected = False

    async def broadcast_room(self, room_id: str) -> None:
        async with self.lock:
            room = self.rooms.get(room_id)
            if not room:
                return
            con = self.connections.get(room_id) or {}
            now = utcnow()
            dead: list[tuple[str, WebSocket]] = []
            for username, ws in list(con.items()):
                snap = room.snapshot(username, now, lambda v: opponent_ink_snapshot(room, v))
                try:
                    await ws.send_json({"type": "state", "payload": snap})
                except Exception:
                    dead.append((username, ws))
            for username, _ in dead:
                con.pop(username, None)

    async def tick_all(self) -> None:
        async with self.lock:
            now = utcnow()
            for room_id, room in list(self.rooms.items()):
                if room.phase == "lobby" and room.can_start_match(now):
                    room.start_match(now)
                elif room.phase == "playing":
                    room.maybe_finish_stall_or_timer(now)
                    if room.phase == "playing":
                        room.process_tick(now)
                    if room.phase == "finished":
                        from app.games.team_territory.rewards import grant_match_rewards

                        grant_match_rewards(room, self._reward_granted)
        for room_id in list(self.rooms.keys()):
            await self.broadcast_room(room_id)

    async def handle_client_message(self, room_id: str, username: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Обработка действия игрока. Возвращает extra ответ для отправителю (опционально)."""
        self.ensure_spelling_words()
        async with self.lock:
            room = self.rooms.get(room_id)
            if not room:
                return {"error": "no_room"}
            now = utcnow()
            t = str(data.get("type") or "")

            if t == "set_ready":
                pl = room.players.get(username)
                if pl and pl.role == "player":
                    pl.ready = bool(data.get("ready"))
                return None

            if t == "claim":
                pl = room.players.get(username)
                if pl and pl.role == "player" and room.phase == "playing":
                    cell = data.get("cell")
                    if isinstance(cell, int):
                        pl.claim_cell = cell
                        pl.claim_submitted = True
                        room.touch_activity(now)
                return None

            if t == "buy_paint":
                return {"defer": "buy_paint", "room_id": room_id, "username": username}

            if t == "challenge_start":
                sess, err = start_challenge_if_allowed(room, username, now, self.spelling_words)
                if err:
                    return {"error": err}
                return {"challenge": sess.to_public_dict(now) if sess else None}

            if t == "challenge_submit":
                ans = data.get("answer")
                seq = data.get("label")
                seq_i = int(seq) if seq is not None and str(seq).isdigit() else None
                out, err = handle_challenge_answer(room, username, now, str(ans) if ans is not None else None, seq_i)
                if err:
                    return {"error": err}
                return {"challenge_result": out}

            if t == "reset_to_lobby":
                if room.phase == "finished":
                    room.reset_to_lobby(now)
                return None

            if t == "set_num_teams":
                if room.phase == "lobby" and not room.players:
                    lo, hi = team_count_bounds()
                    n = int(data.get("num_teams") or 2)
                    room.num_teams = max(lo, min(hi, n))
                return None

            return None


team_territory_manager = TeamTerritoryManager()

_tick_task: asyncio.Task[None] | None = None


async def team_territory_background_loop() -> None:
    while True:
        await asyncio.sleep(0.25)
        try:
            await team_territory_manager.tick_all()
        except Exception:
            pass


def start_team_territory_background_loop() -> None:
    global _tick_task
    if _tick_task is not None and not _tick_task.done():
        return
    _tick_task = asyncio.create_task(team_territory_background_loop(), name="team_territory_tick")


async def stop_team_territory_background_loop() -> None:
    global _tick_task
    if _tick_task is None or _tick_task.done():
        _tick_task = None
        return
    _tick_task.cancel()
    try:
        await _tick_task
    except asyncio.CancelledError:
        pass
    _tick_task = None
