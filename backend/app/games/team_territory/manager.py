"""In-memory комнаты Team Territory + рассылка WS."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from fastapi import WebSocket

from app.core.config import settings
from app.games.team_territory.challenge import load_spelling_words, normalize_spelling_locale
from app.games.team_territory.debug import try_debug_row1_cheat_finish
from app.games.team_territory.room_engine import (
    TerritoryRoom,
    add_player,
    claim_paint_cost,
    handle_challenge_answer,
    opponent_ink_snapshot,
    start_challenge_if_allowed,
    utcnow,
)
from app.games.team_territory.teams import team_count_bounds

logger = logging.getLogger(__name__)


@dataclass
class TeamTerritoryManager:
    rooms: dict[str, TerritoryRoom] = field(default_factory=dict)
    connections: dict[str, dict[str, WebSocket]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    spelling_words_by_locale: dict[str, list[str]] = field(default_factory=dict)
    _reward_granted: set[str] = field(default_factory=set)  # match_id:username in-memory guard

    def spelling_words_for(self, locale: str) -> list[str]:
        loc = normalize_spelling_locale(locale)
        if loc not in self.spelling_words_by_locale:
            from app.games.team_territory.constants import tt_params

            self.spelling_words_by_locale[loc] = load_spelling_words(tt_params(), loc)
        return self.spelling_words_by_locale[loc]

    def get_or_create_room(self, room_id: str, num_teams: int = 4) -> TerritoryRoom:
        lo, hi = team_count_bounds()
        nt = max(lo, min(hi, int(num_teams)))
        if room_id not in self.rooms:
            self.rooms[room_id] = TerritoryRoom(room_id=room_id, num_teams=nt)
        r = self.rooms[room_id]
        if r.num_teams != nt and r.phase == "lobby":
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
                if room.phase == "lobby":
                    if room.lobby_idle_expired(now):
                        room.reset_idle_lobby(now)
                    elif room.can_start_match(now):
                        room.start_match(now)
                elif room.phase == "playing":
                    room.maybe_finish_stall_or_timer(now)
                    if room.phase == "playing":
                        room.process_tick(now)
                    if room.phase == "finished":
                        from app.games.team_territory.rewards import grant_match_rewards

                        logger.info(
                            "team_territory_reward: tick_all calling grant room=%s match_id=%s "
                            "finish_reason=%s",
                            room.room_id,
                            room.match_id,
                            room.finish_reason,
                        )
                        grant_match_rewards(room, self._reward_granted)
        for room_id in list(self.rooms.keys()):
            await self.broadcast_room(room_id)

    async def handle_client_message(self, room_id: str, username: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Обработка действия игрока. Возвращает extra ответ для отправителю (опционально)."""
        async with self.lock:
            room = self.rooms.get(room_id)
            if not room:
                return {"error": "no_room"}
            now = utcnow()
            t = str(data.get("type") or "")

            if t == "set_ready":
                pl = room.players.get(username)
                if pl and pl.role == "player" and room.phase == "lobby":
                    want_ready = bool(data.get("ready"))
                    if want_ready and room.lobby_teams_imbalanced():
                        return {"error": "teams_imbalanced"}
                    pl.ready = want_ready
                    if room.can_start_match(now):
                        room.start_match(now)
                return None

            if t == "set_team":
                pl = room.players.get(username)
                if not pl or pl.role != "player" or room.phase != "lobby":
                    return {"error": "not_lobby"}
                tid = data.get("team_id")
                if not isinstance(tid, int) or not (0 <= tid < room.num_teams):
                    return {"error": "bad_team"}
                pl.team_id = tid
                pl.ready = False
                return None

            if t == "claim":
                pl = room.players.get(username)
                if pl and pl.role == "player" and room.phase == "playing":
                    cell = data.get("cell")
                    if isinstance(cell, int):
                        cost = claim_paint_cost(room, cell, pl.team_id)
                        if cost is None:
                            return {"error": "invalid_claim"}
                        if pl.paint < cost:
                            return {"error": "not_enough_paint"}
                        pl.claim_cell = cell
                        pl.claim_submitted = True
                        room.touch_activity(now, team_id=pl.team_id)
                        if try_debug_row1_cheat_finish(room, username, cell, now):
                            logger.info(
                                "team_territory_reward: debug cheat triggered via claim room=%s user=%s",
                                room_id,
                                username,
                            )
                            from app.games.team_territory.rewards import grant_match_rewards

                            grant_match_rewards(room, self._reward_granted)
                            return {"debug_cheat_win": True}
                return None

            if t == "buy_paint":
                return {"defer": "buy_paint", "room_id": room_id, "username": username}

            if t == "challenge_start":
                locale = normalize_spelling_locale(str(data.get("locale") or "en"))
                words = self.spelling_words_for(locale)
                sess, err = start_challenge_if_allowed(room, username, now, words)
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

            if t == "invite_players":
                pl = room.players.get(username)
                if not pl or room.phase != "lobby":
                    return {"error": "not_lobby"}
                if room.invite_cooldown_until and now < room.invite_cooldown_until:
                    return {"error": "invite_cooldown"}
                room.invite_cooldown_until = now + timedelta(seconds=120)
                room.invite_broadcast_until = now + timedelta(seconds=8)
                room.invite_broadcast_by = username
                return None

            if t == "set_num_teams":
                if room.phase == "lobby" and not room.players:
                    lo, hi = team_count_bounds()
                    n = int(data.get("num_teams") or 4)
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
