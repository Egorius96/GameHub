from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field

from app.games.rps.logic import Move, normalize_move, outcome, random_move
from app.integrations.users_api import users_api

MIN_TOTAL_SEC = 38.0
MIN_GAP_SEC = 10.0
TARGET_WINS = 3
ROUND_PICK_SEC = 5.0
ROUND_REVEAL_SEC = 5.0


@dataclass
class RobotSession:
    username: str
    started_mono: float
    last_play_mono: float
    player_wins: int = 0
    robot_wins: int = 0
    rounds: list[dict] = field(default_factory=list)
    finished: bool = False
    player_won_match: bool = False
    reward_granted: bool = False
    phase: str = "picking"  # picking | revealing
    pick_deadline_mono: float = 0.0
    reveal_deadline_mono: float = 0.0
    pending_move: Move | None = None
    last_round: dict | None = None


class RobotSessionManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_id: dict[str, RobotSession] = {}

    def _begin_pick(self, s: RobotSession) -> None:
        now = time.monotonic()
        s.phase = "picking"
        s.pick_deadline_mono = now + ROUND_PICK_SEC
        s.reveal_deadline_mono = 0.0
        s.pending_move = None
        s.last_round = None

    def _session_payload(self, s: RobotSession) -> dict:
        now = time.monotonic()
        pick_left = max(0.0, s.pick_deadline_mono - now) if s.phase == "picking" else 0.0
        reveal_left = max(0.0, s.reveal_deadline_mono - now) if s.phase == "revealing" else 0.0
        return {
            "phase": s.phase,
            "pick_seconds_left": round(pick_left, 2),
            "reveal_seconds_left": round(reveal_left, 2),
            "pending_move": s.pending_move,
            "last_round": s.last_round,
            "player_wins": s.player_wins,
            "robot_wins": s.robot_wins,
            "finished": s.finished,
        }

    def start(self, username: str) -> dict:
        now = time.monotonic()
        sid = secrets.token_urlsafe(16)
        with self._lock:
            s = RobotSession(
                username=username,
                started_mono=now,
                last_play_mono=now - MIN_GAP_SEC,
            )
            self._begin_pick(s)
            self._by_id[sid] = s
        return {
            "session_id": sid,
            "target_wins": TARGET_WINS,
            "min_total_sec": MIN_TOTAL_SEC,
            "round_pick_sec": ROUND_PICK_SEC,
            "round_reveal_sec": ROUND_REVEAL_SEC,
            **self._session_payload(s),
        }

    def _get(self, sid: str, username: str) -> RobotSession | None:
        s = self._by_id.get(sid)
        if s is None or s.username != username:
            return None
        return s

    def pick(self, sid: str, username: str, move_raw: str) -> dict:
        mv = normalize_move(move_raw)
        if mv is None:
            return {"ok": False, "error": "invalid_move"}
        with self._lock:
            s = self._get(sid, username)
            if s is None:
                return {"ok": False, "error": "session_not_found"}
            if s.finished:
                return {"ok": False, "error": "session_finished"}
            if s.phase != "picking":
                return {"ok": False, "error": "not_picking"}
            s.pending_move = mv
            return {"ok": True, **self._session_payload(s)}

    def _resolve_round_locked(self, s: RobotSession, *, forfeit: bool) -> dict:
        now = time.monotonic()
        bot: Move = random_move()
        if forfeit or s.pending_move is None:
            mv = s.pending_move
            winner_side = "robot"
            player_move = mv
            s.robot_wins += 1
        else:
            mv = s.pending_move
            res = outcome(mv, bot)
            player_move = mv
            if res == 0:
                winner_side = "tie"
            elif res == 1:
                s.player_wins += 1
                winner_side = "player"
            else:
                s.robot_wins += 1
                winner_side = "robot"

        if winner_side == "tie":
            pass
        s.rounds.append(
            {
                "player": player_move,
                "robot": bot,
                "winner_side": winner_side,
                "forfeit": forfeit or player_move is None,
                "player_wins": s.player_wins,
                "robot_wins": s.robot_wins,
            }
        )
        s.last_play_mono = now
        s.last_round = {
            "player": player_move,
            "robot": bot,
            "winner_side": winner_side,
            "forfeit": forfeit or player_move is None,
        }
        s.phase = "revealing"
        s.reveal_deadline_mono = now + ROUND_REVEAL_SEC
        s.pending_move = None

        reward: dict = {"granted": False}
        if s.player_wins >= TARGET_WINS or s.robot_wins >= TARGET_WINS:
            s.finished = True
            s.player_won_match = s.player_wins >= TARGET_WINS
            elapsed = now - s.started_mono
            if s.player_won_match:
                if elapsed >= MIN_TOTAL_SEC and not s.reward_granted:
                    new_bal = users_api.increment_diamonds(s.username, 1)
                    s.reward_granted = new_bal is not None
                    reward = {"granted": s.reward_granted, "diamonds": new_bal}
                else:
                    reward = {
                        "granted": False,
                        "wait_seconds": max(0.0, round(MIN_TOTAL_SEC - elapsed, 2)),
                    }
            else:
                reward = {"granted": False, "lost": True}

        return {
            "ok": True,
            "robot": bot,
            "player_move": player_move,
            "winner_side": winner_side,
            "forfeit": forfeit or player_move is None,
            "player_wins": s.player_wins,
            "robot_wins": s.robot_wins,
            "finished": s.finished,
            "player_won_match": s.player_won_match,
            "reward": reward,
            **self._session_payload(s),
        }

    def resolve(self, sid: str, username: str) -> dict:
        with self._lock:
            s = self._get(sid, username)
            if s is None:
                return {"ok": False, "error": "session_not_found"}
            if s.finished:
                return {"ok": False, "error": "session_finished"}
            if s.phase != "picking":
                return {"ok": False, "error": "not_picking"}
            forfeit = s.pending_move is None
            return self._resolve_round_locked(s, forfeit=forfeit)

    def tick(self, sid: str, username: str) -> dict | None:
        """Авто-резолв по таймеру (вызывается с клиента или при poll)."""
        with self._lock:
            s = self._get(sid, username)
            if s is None or s.finished:
                return None
            now = time.monotonic()
            if s.phase == "picking" and now >= s.pick_deadline_mono:
                forfeit = s.pending_move is None
                return self._resolve_round_locked(s, forfeit=forfeit)
            if s.phase == "revealing" and now >= s.reveal_deadline_mono:
                if not s.finished:
                    self._begin_pick(s)
                return {"ok": True, "advanced": True, **self._session_payload(s)}
        return None

    def next_round(self, sid: str, username: str) -> dict:
        with self._lock:
            s = self._get(sid, username)
            if s is None:
                return {"ok": False, "error": "session_not_found"}
            if s.finished:
                return {"ok": False, "error": "session_finished"}
            now = time.monotonic()
            if s.phase == "revealing" and now < s.reveal_deadline_mono:
                return {
                    "ok": False,
                    "error": "reveal_not_done",
                    "reveal_seconds_left": round(s.reveal_deadline_mono - now, 2),
                }
            if s.phase == "picking":
                return {"ok": True, **self._session_payload(s)}
            self._begin_pick(s)
            return {"ok": True, **self._session_payload(s)}

    def state(self, sid: str, username: str) -> dict:
        with self._lock:
            s = self._get(sid, username)
            if s is None:
                return {"ok": False, "error": "session_not_found"}
            tick_out = None
            now = time.monotonic()
            if s.phase == "picking" and now >= s.pick_deadline_mono:
                tick_out = self._resolve_round_locked(s, forfeit=s.pending_move is None)
            elif s.phase == "revealing" and now >= s.reveal_deadline_mono and not s.finished:
                self._begin_pick(s)
                tick_out = {"ok": True, "advanced": True, **self._session_payload(s)}
            base = {"ok": True, **self._session_payload(s)}
            if tick_out:
                base["tick"] = tick_out
            return base

    def play(self, sid: str, username: str, move_raw: str) -> dict:
        """Совместимость: pick + немедленный resolve (устаревший путь)."""
        pick_out = self.pick(sid, username, move_raw)
        if not pick_out.get("ok"):
            return pick_out
        return self.resolve(sid, username)

    def claim(self, sid: str, username: str) -> dict:
        now = time.monotonic()
        with self._lock:
            s = self._get(sid, username)
            if s is None:
                return {"ok": False, "error": "session_not_found"}
            if not s.finished or not s.player_won_match:
                return {"ok": False, "error": "nothing_to_claim"}
            if s.reward_granted:
                return {"ok": True, "already_granted": True}
            elapsed = now - s.started_mono
            if elapsed < MIN_TOTAL_SEC:
                return {
                    "ok": False,
                    "error": "too_fast_total",
                    "wait_seconds": max(0.0, round(MIN_TOTAL_SEC - elapsed, 2)),
                }
            new_bal = users_api.increment_diamonds(s.username, 1)
            if new_bal is None:
                return {"ok": False, "error": "grant_failed"}
            s.reward_granted = True
            return {"ok": True, "granted": True, "diamonds": new_bal}


robot_sessions = RobotSessionManager()
