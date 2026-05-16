from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from app.games.rps.logic import normalize_move, outcome
from app.integrations.users_api import users_api

NUM_ROOMS = 5
ONLINE_TARGET_WINS = 5
PICK_SEC = 5.0
REVEAL_SEC = 5.0


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RpsRoom:
    def __init__(self, room_id: int) -> None:
        self.id = room_id
        self.lock = asyncio.Lock()
        self.clients: dict[str, WebSocket] = {}
        self.order: list[str] = []
        self.chat: list[dict[str, Any]] = []
        self.phase: str = "waiting"  # waiting | betting | playing
        self.bets: dict[str, int | None] = {}
        self.ready: dict[str, bool] = {}
        self.pot: int = 0
        self.stakes: dict[str, int] = {}
        self.wins: dict[str, int] = {}
        self.choices: dict[str, str | None] = {}
        self.round_idx: int = 0
        self.round_deadline_mono: float | None = None
        self.reveal_deadline_mono: float | None = None
        self.round_phase: str = "pick"  # pick | reveal
        self.last_round: dict[str, Any] | None = None

    def occupancy(self) -> int:
        return len(self.clients)

    def _ensure_member_keys(self) -> None:
        for u in self.order:
            self.bets.setdefault(u, None)
            self.ready.setdefault(u, False)

    def _reset_match_to_betting(self) -> None:
        self.phase = "betting"
        self.pot = 0
        self.stakes.clear()
        self.wins.clear()
        self.choices.clear()
        self.round_idx = 0
        self.round_deadline_mono = None
        self.reveal_deadline_mono = None
        self.round_phase = "pick"
        for u in self.order:
            self.bets[u] = None
            self.ready[u] = False

    def snapshot_public(self) -> dict[str, Any]:
        occ = self.occupancy()
        return {"room_id": self.id, "occupancy": occ}

    def snapshot_for(self, username: str) -> dict[str, Any]:
        now = time.monotonic()
        pick_left = (
            max(0.0, self.round_deadline_mono - now)
            if self.phase == "playing" and self.round_phase == "pick" and self.round_deadline_mono
            else 0.0
        )
        reveal_left = (
            max(0.0, self.reveal_deadline_mono - now)
            if self.phase == "playing" and self.round_phase == "reveal" and self.reveal_deadline_mono
            else 0.0
        )
        other = next((u for u in self.order if u != username), None)
        your_choice = self.choices.get(username) if self.phase == "playing" else None
        opp_choice = None
        if self.phase == "playing" and other:
            if self.round_phase == "reveal":
                opp_choice = self.choices.get(other)
            elif self.round_phase == "pick":
                opp_choice = None
        return {
            "room_id": self.id,
            "occupancy": self.occupancy(),
            "phase": self.phase,
            "players": list(self.order),
            "you": username,
            "chat": list(self.chat),
            "bets": {k: self.bets.get(k) for k in self.order},
            "ready": {k: bool(self.ready.get(k)) for k in self.order},
            "pot": self.pot,
            "stakes": dict(self.stakes),
            "wins": {k: int(self.wins.get(k, 0)) for k in self.order},
            "target_wins": ONLINE_TARGET_WINS,
            "round": self.round_idx,
            "round_phase": self.round_phase if self.phase == "playing" else None,
            "your_choice": your_choice,
            "opponent_choice": opp_choice,
            "pick_seconds_left": round(pick_left, 2),
            "reveal_seconds_left": round(reveal_left, 2),
            "last_round": self.last_round,
        }

    async def broadcast(self, payload: dict[str, Any]) -> None:
        dead: list[str] = []
        for uname, ws in list(self.clients.items()):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(uname)
        for u in dead:
            self.clients.pop(u, None)
            if u in self.order:
                self.order.remove(u)

    async def send_all_states(self) -> None:
        for u, ws in list(self.clients.items()):
            try:
                await ws.send_json({"type": "room.state", "payload": self.snapshot_for(u)})
            except Exception:
                pass

    async def add_client(self, username: str, ws: WebSocket) -> str | None:
        """None = ok. Иначе код ошибки."""
        async with self.lock:
            if username in self.clients:
                try:
                    await self.clients[username].close(code=4000)
                except Exception:
                    pass
                self.clients.pop(username, None)
                if username in self.order:
                    self.order.remove(username)
            if len(self.clients) >= 2:
                return "room_full"
            self.clients[username] = ws
            if username not in self.order:
                self.order.append(username)
            self._ensure_member_keys()
            if len(self.order) == 2:
                self.phase = "betting"
                for u in self.order:
                    self.bets[u] = None
                    self.ready[u] = False
            else:
                self.phase = "waiting"
            await self.send_all_states()
        return None

    async def remove_client(self, username: str) -> None:
        async with self.lock:
            forfeit_winner: str | None = None
            if (
                self.phase == "playing"
                and self.pot > 0
                and username in self.order
                and len(self.order) == 2
            ):
                forfeit_winner = next((u for u in self.order if u != username), None)

            ws = self.clients.pop(username, None)
            if ws:
                try:
                    await ws.close()
                except Exception:
                    pass
            if username in self.order:
                self.order.remove(username)

            if forfeit_winner and forfeit_winner in self.clients:
                users_api.adjust_diamonds(forfeit_winner, self.pot)
                self._reset_match_to_betting()
                self.last_round = {
                    "kind": "forfeit",
                    "winner": forfeit_winner,
                    "reason": "opponent_disconnected",
                }
            elif self.phase == "playing":
                self._reset_match_to_betting()

            if not self.order:
                self.phase = "waiting"
                self.chat.clear()
                self.bets.clear()
                self.ready.clear()
                self.pot = 0
                self.stakes.clear()
                self.wins.clear()
                self.choices.clear()
                self.round_idx = 0
                self.round_deadline_mono = None
                self.reveal_deadline_mono = None
                self.round_phase = "pick"
                self.last_round = None

            await self.send_all_states()

    async def _start_playing_locked(self) -> str | None:
        if len(self.order) != 2:
            return "need_two_players"
        a, b = self.order[0], self.order[1]
        ba, bb = self.bets.get(a), self.bets.get(b)
        if ba is None or bb is None:
            return "bets_incomplete"
        if not (1 <= ba <= 5 and 1 <= bb <= 5):
            return "bad_bet_range"
        if not self.ready.get(a) or not self.ready.get(b):
            return "not_ready"
        if users_api.get_diamond_balance(a) is None or users_api.get_diamond_balance(b) is None:
            return "user_missing"
        if int(users_api.get_diamond_balance(a) or 0) < ba:  # type: ignore[arg-type]
            return "not_enough_a"
        if int(users_api.get_diamond_balance(b) or 0) < bb:
            return "not_enough_b"

        r1 = users_api.adjust_diamonds(a, -ba)
        if r1 is None:
            return "pay_fail_a"
        r2 = users_api.adjust_diamonds(b, -bb)
        if r2 is None:
            users_api.adjust_diamonds(a, ba)
            return "pay_fail_b"

        self.phase = "playing"
        self.stakes = {a: ba, b: bb}
        self.pot = ba + bb
        self.wins = {a: 0, b: 0}
        self.round_idx = 1
        self.choices = {a: None, b: None}
        self.round_phase = "pick"
        self.round_deadline_mono = time.monotonic() + PICK_SEC
        self.reveal_deadline_mono = None
        self.last_round = None
        return None

    def _begin_pick_locked(self) -> None:
        if len(self.order) != 2:
            return
        a, b = self.order[0], self.order[1]
        self.round_phase = "pick"
        self.choices = {a: None, b: None}
        self.round_deadline_mono = time.monotonic() + PICK_SEC
        self.reveal_deadline_mono = None

    async def _resolve_round_locked(self, *, forfeit_a: bool = False, forfeit_b: bool = False) -> None:
        if len(self.order) != 2:
            return
        a, b = self.order[0], self.order[1]
        ca = normalize_move(str(self.choices.get(a) or "")) if not forfeit_a else None
        cb = normalize_move(str(self.choices.get(b) or "")) if not forfeit_b else None

        winner_name: str | None = None
        side = "tie"
        if ca is None and cb is None:
            winner_name = None
            side = "tie"
        elif ca is None:
            winner_name = b
            side = "b"
        elif cb is None:
            winner_name = a
            side = "a"
        else:
            res = outcome(ca, cb)
            if res == 0:
                winner_name = None
                side = "tie"
            elif res == 1:
                winner_name = a
                side = "a"
            else:
                winner_name = b
                side = "b"

        if winner_name:
            self.wins[winner_name] = int(self.wins.get(winner_name, 0)) + 1

        self.last_round = {
            "player_a": a,
            "player_b": b,
            "move_a": ca,
            "move_b": cb,
            "winner": winner_name,
            "side": side,
            "forfeit_a": forfeit_a or ca is None,
            "forfeit_b": forfeit_b or cb is None,
        }

        done = (
            winner_name is not None
            and int(self.wins.get(winner_name, 0)) >= ONLINE_TARGET_WINS
        )
        if done and winner_name:
            users_api.adjust_diamonds(winner_name, self.pot)
            lr = {
                **(self.last_round or {}),
                "match_over": True,
                "match_winner": winner_name,
            }
            self._reset_match_to_betting()
            self.last_round = lr
        else:
            self.round_phase = "reveal"
            self.round_deadline_mono = None
            self.reveal_deadline_mono = time.monotonic() + REVEAL_SEC

    async def handle_chat(self, username: str, text: str) -> None:
        t = str(text or "").strip()[:400]
        if not t:
            return
        async with self.lock:
            if username not in self.clients:
                return
            self.chat.append({"from": username, "text": t, "at": _utc_iso()})
            self.chat = self.chat[-200:]
            await self.broadcast({"type": "room.chat", "payload": {"messages": list(self.chat)}})

    async def handle_bet_ready(self, username: str, bet: int | None, ready_flag: bool) -> None:
        async with self.lock:
            if username not in self.clients or self.phase != "betting":
                return
            self._ensure_member_keys()
            if bet is not None:
                if 1 <= int(bet) <= 5:
                    self.bets[username] = int(bet)
            if ready_flag:
                self.ready[username] = True

            if len(self.order) == 2 and all(self.ready.get(u) for u in self.order):
                err = await self._start_playing_locked()
                if err:
                    for u in self.order:
                        self.ready[u] = False
                    for u, cws in list(self.clients.items()):
                        try:
                            await cws.send_json({"type": "room.error", "message": err})
                        except Exception:
                            pass
                    await self.send_all_states()
                    return
                await self.send_all_states()
                return
            await self.send_all_states()

    async def handle_pick(self, username: str, move_raw: str) -> None:
        async with self.lock:
            if self.phase != "playing" or self.round_phase != "pick" or username not in self.order:
                return
            mv = normalize_move(move_raw)
            if mv is None:
                return
            self.choices[username] = mv
            if len(self.order) == 2:
                a, b = self.order[0], self.order[1]
                if self.choices.get(a) and self.choices.get(b):
                    await self._resolve_round_locked()
                    await self.send_all_states()
                    return
            await self.send_all_states()

    async def handle_throw(self, username: str, move_raw: str) -> None:
        await self.handle_pick(username, move_raw)

    async def tick(self) -> None:
        async with self.lock:
            if self.phase != "playing" or len(self.order) != 2:
                return
            now = time.monotonic()
            a, b = self.order[0], self.order[1]
            if self.round_phase == "pick" and self.round_deadline_mono and now >= self.round_deadline_mono:
                fa = not self.choices.get(a)
                fb = not self.choices.get(b)
                if self.choices.get(a) and self.choices.get(b):
                    return
                await self._resolve_round_locked(forfeit_a=fa, forfeit_b=fb)
                await self.send_all_states()
                return
            if self.round_phase == "reveal" and self.reveal_deadline_mono and now >= self.reveal_deadline_mono:
                self.round_idx += 1
                self._begin_pick_locked()
                await self.send_all_states()


class RpsRoomManager:
    def __init__(self) -> None:
        self.rooms = [RpsRoom(i) for i in range(NUM_ROOMS)]

    def public_lobby_snapshot(self) -> list[dict[str, Any]]:
        return [r.snapshot_public() for r in self.rooms]

    async def connect(self, room_id: int, username: str, ws: WebSocket) -> str | None:
        if room_id < 0 or room_id >= NUM_ROOMS:
            return "bad_room"
        return await self.rooms[room_id].add_client(username, ws)

    async def disconnect(self, room_id: int, username: str) -> None:
        if 0 <= room_id < NUM_ROOMS:
            await self.rooms[room_id].remove_client(username)

    async def dispatch_message(self, room_id: int, username: str, data: dict[str, Any]) -> None:
        if not (0 <= room_id < NUM_ROOMS):
            return
        room = self.rooms[room_id]
        t = str(data.get("type") or "")
        if t == "chat":
            await room.handle_chat(username, str(data.get("text") or ""))
        elif t == "bet_ready":
            bet = data.get("bet")
            b_int = int(bet) if bet is not None and str(bet).isdigit() else None
            await room.handle_bet_ready(username, b_int, bool(data.get("ready")))
        elif t in ("throw", "pick"):
            await room.handle_pick(username, str(data.get("choice") or data.get("move") or ""))

    async def tick_room(self, room_id: int) -> None:
        if 0 <= room_id < NUM_ROOMS:
            await self.rooms[room_id].tick()


rps_room_manager = RpsRoomManager()
