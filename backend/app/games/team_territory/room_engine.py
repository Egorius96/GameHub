"""Состояние комнаты Team Territory и обработка тиков."""

from __future__ import annotations

import random
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.core.config import settings
from app.games.team_territory.challenge import ChallengeSession, load_spelling_words, pick_mode
from app.games.team_territory.constants import TeamTerritoryParams, tt_params
from app.games.team_territory.grid import cap_c_for_tick, cell_total, grid_size_from_P
from app.games.team_territory.teams import assign_team_id, teams_public_meta


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PlayerSlot:
    username: str
    team_id: int
    role: str  # "player" | "spectator"
    ready: bool = False
    connected: bool = True
    join_order: int = 0
    paint: int = 0
    personal_cells: int = 0
    claim_cell: int | None = None
    next_regen_at: datetime | None = None
    ticks_in_match: int = 0
    buys_in_match: int = 0
    challenges_started_match: int = 0
    last_challenge_started_at: datetime | None = None
    challenge: ChallengeSession | None = None
    claim_submitted: bool = False

    def is_active_player(self) -> bool:
        return self.role == "player" and self.connected


@dataclass
class TerritoryRoom:
    room_id: str
    num_teams: int
    phase: str = "lobby"  # lobby | playing | finished
    created_at: datetime = field(default_factory=utcnow)
    players: dict[str, PlayerSlot] = field(default_factory=dict)
    spectator_queue_next: list[str] = field(default_factory=list)
    cells: list[int] = field(default_factory=list)
    g: int = 10
    tick_index: int = 0
    next_tick_at: datetime | None = None
    match_started_at: datetime | None = None
    match_end_at: datetime | None = None
    match_id: str = ""
    last_significant_activity_at: datetime | None = None
    stall_warn_deadline_at: datetime | None = None
    stall_hard_deadline_at: datetime | None = None
    stall_phase: str = "none"  # none | warn | idle
    finish_reason: str | None = None
    winning_team_ids: list[int] = field(default_factory=list)
    scores: dict[int, int] = field(default_factory=dict)
    ready_deadline_at: datetime | None = None
    join_seq: int = 0
    _rng: random.Random = field(default_factory=lambda: random.Random(secrets.randbits(128)))

    def params(self) -> TeamTerritoryParams:
        return tt_params()

    def active_players(self) -> list[PlayerSlot]:
        return [p for p in self.players.values() if p.role == "player"]

    def ready_players(self) -> list[PlayerSlot]:
        return [p for p in self.active_players() if p.ready]

    def teams_represented(self, plist: list[PlayerSlot]) -> set[int]:
        return {p.team_id for p in plist}

    def can_start_match(self, now: datetime) -> bool:
        p = self.params()
        ready = self.ready_players()
        if len(ready) < 1:
            return False
        teams = self.teams_represented(ready)
        debug = settings.team_territory_debug_solo_lobby and settings.gamehub_env != "production"
        if debug:
            return len(self.active_players()) >= 1
        if len(self.active_players()) < max(2, p.min_participants):
            return False
        if len(ready) < 2:
            return False
        if len(teams) < 2:
            return False
        if self.ready_deadline_at and now >= self.ready_deadline_at:
            return True
        return all(p.ready for p in self.active_players())

    def start_match(self, now: datetime) -> None:
        p = self.params()
        participants = [x for x in self.active_players() if x.ready]
        if settings.team_territory_debug_solo_lobby and settings.gamehub_env != "production":
            participants = list(self.active_players())
            if not participants:
                return
        elif len(participants) < 2 or len(self.teams_represented(participants)) < 2:
            return
        self.match_id = str(uuid.uuid4())
        self.g = grid_size_from_P(len(participants), p)
        ct = cell_total(self.g)
        self.cells = [-1] * ct
        self.tick_index = 0
        self.phase = "playing"
        self.match_started_at = now
        self.match_end_at = now + timedelta(seconds=p.match_max_sec)
        self.next_tick_at = now + timedelta(milliseconds=p.tick_ms)
        self.last_significant_activity_at = now
        self.stall_phase = "none"
        self.stall_warn_deadline_at = None
        self.stall_hard_deadline_at = None
        self.finish_reason = None
        self.winning_team_ids = []
        self.scores = {i: 0 for i in range(self.num_teams)}
        for pl in self.players.values():
            pl.claim_cell = None
            if pl in participants:
                pl.paint = p.paint_max
                pl.next_regen_at = now + timedelta(seconds=p.regen_sec)
                pl.ticks_in_match = 0
                pl.buys_in_match = 0
                pl.challenges_started_match = 0
                pl.last_challenge_started_at = None
                pl.challenge = None
            elif pl.role == "player":
                # не готов к старту — переводим в наблюдатели
                pl.role = "spectator"
                pl.ready = False
                pl.paint = 0
                pl.claim_cell = None
        self._update_stall_deadlines(now)

    def touch_activity(self, now: datetime) -> None:
        self.last_significant_activity_at = now
        self.stall_phase = "none"
        if self.phase == "playing":
            self._update_stall_deadlines(now)

    def _update_stall_deadlines(self, now: datetime) -> None:
        p = self.params()
        base = self.last_significant_activity_at or now
        self.stall_warn_deadline_at = base + timedelta(seconds=p.match_stall_idle_sec - p.match_stall_warn_before_sec)
        self.stall_hard_deadline_at = base + timedelta(seconds=p.match_stall_idle_sec)

    def maybe_finish_stall_or_timer(self, now: datetime) -> None:
        if self.phase != "playing":
            return
        if self.stall_hard_deadline_at and now >= self.stall_hard_deadline_at:
            self._finish_match(now, "stale_idle")
            return
        if self.stall_warn_deadline_at and now >= self.stall_warn_deadline_at and self.stall_phase == "none":
            self.stall_phase = "warn"
        if self.match_end_at and now >= self.match_end_at:
            self._finish_match(now, "time_up")
            return
        if all(c >= 0 for c in self.cells):
            self._finish_match(now, "board_full")

    def _finish_match(self, now: datetime, reason: str) -> None:
        self.phase = "finished"
        self.finish_reason = reason
        for t in range(self.num_teams):
            self.scores[t] = sum(1 for c in self.cells if c == t)
        best = max(self.scores.values()) if self.scores else 0
        self.winning_team_ids = [tid for tid, sc in self.scores.items() if sc == best and best > 0]
        if reason == "stale_idle":
            self.winning_team_ids = []

    def process_tick(self, now: datetime) -> dict[str, Any]:
        """Закрывает тик если наступило время. Возвращает краткий лог события."""
        if self.phase != "playing" or self.next_tick_at is None or now < self.next_tick_at:
            return {"applied": False}
        p = self.params()
        log: dict[str, Any] = {"applied": True, "tick_index": self.tick_index}

        active = [x for x in self.active_players() if x.connected]
        for pl in active:
            if pl.claim_submitted:
                pl.ticks_in_match += 1
                pl.claim_submitted = False

        # регген краски
        for pl in self.active_players():
            if pl.next_regen_at is None:
                continue
            while now >= pl.next_regen_at and pl.paint < p.paint_max:
                pl.paint += 1
                pl.next_regen_at = pl.next_regen_at + timedelta(seconds=p.regen_sec)

        ct = cell_total(self.g)
        active = [x for x in self.active_players() if x.connected]
        n_players = len(active)
        c_cap = cap_c_for_tick(p, ct, n_players)

        # заявки: (username, cell, team_id, personal_cells)
        raw: list[dict[str, Any]] = []
        for pl in active:
            if pl.claim_cell is None:
                continue
            cell = pl.claim_cell
            if not (0 <= cell < len(self.cells)) or self.cells[cell] != -1 or pl.paint < 1:
                continue
            raw.append(
                {
                    "username": pl.username,
                    "cell": cell,
                    "team_id": pl.team_id,
                    "personal_cells": pl.personal_cells,
                }
            )

        # конфликт по клетке — один победитель
        by_cell: dict[int, list[dict[str, Any]]] = {}
        for it in raw:
            by_cell.setdefault(it["cell"], []).append(it)
        survivors: list[dict[str, Any]] = []
        for cell, group in by_cell.items():
            survivors.append(self._pick_weighted(group))

        winners = self._cap_claims(survivors, c_cap)

        for pl in active:
            pl.claim_cell = None

        for w in winners:
            pl = self.players.get(w["username"])
            if pl is None:
                continue
            cell = w["cell"]
            if not (0 <= cell < len(self.cells)) or self.cells[cell] != -1 or pl.paint < 1:
                continue
            self.cells[cell] = pl.team_id
            pl.paint -= 1
            pl.personal_cells += 1

        self.tick_index += 1
        self.next_tick_at = now + timedelta(milliseconds=p.tick_ms)
        log["painted"] = len(winners)

        self.maybe_finish_stall_or_timer(now)
        return log

    def _pick_weighted(self, group: list[dict[str, Any]]) -> dict[str, Any]:
        if len(group) == 1:
            return group[0]
        total = sum(1.0 / (1 + int(x["personal_cells"])) for x in group)
        r = self._rng.random() * total
        acc = 0.0
        for x in group:
            acc += 1.0 / (1 + int(x["personal_cells"]))
            if r <= acc:
                return x
        return group[-1]

    def _cap_claims(self, items: list[dict[str, Any]], cap: int) -> list[dict[str, Any]]:
        if len(items) <= cap:
            return items
        pool = list(items)
        out: list[dict[str, Any]] = []
        while pool and len(out) < cap:
            total = sum(1.0 / (1 + int(x["personal_cells"])) for x in pool)
            r = self._rng.random() * total
            acc = 0.0
            chosen = pool[-1]
            for x in pool:
                acc += 1.0 / (1 + int(x["personal_cells"]))
                if r <= acc:
                    chosen = x
                    break
            out.append(chosen)
            pool = [x for x in pool if x["username"] != chosen["username"]]
        return out

    def reset_to_lobby(self, now: datetime) -> None:
        self.phase = "lobby"
        self.cells = []
        self.tick_index = 0
        self.next_tick_at = None
        self.match_started_at = None
        self.match_end_at = None
        self.match_id = ""
        self.finish_reason = None
        self.winning_team_ids = []
        self.scores = {}
        self.stall_phase = "none"
        self.stall_warn_deadline_at = None
        self.stall_hard_deadline_at = None
        self.last_significant_activity_at = None
        for u in list(self.spectator_queue_next):
            pl = self.players.get(u)
            if pl and pl.role == "spectator":
                pl.role = "player"
        self.spectator_queue_next.clear()
        for pl in self.players.values():
            pl.ready = False
            pl.claim_cell = None
            pl.paint = 0
        p = self.params()
        self.ready_deadline_at = now + timedelta(seconds=p.ready_timeout_sec)

    def snapshot(
        self,
        viewer: str,
        now: datetime,
        opponent_ink_for: Callable[[str], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        p = self.params()
        me = self.players.get(viewer)
        teams = teams_public_meta(self.num_teams)
        opp_ink: dict[str, Any] = {"sum": 0, "by_team": {}}
        if opponent_ink_for:
            opp_ink = opponent_ink_for(viewer)
        stall_deadline_iso = None
        if self.stall_phase == "warn" and self.stall_hard_deadline_at:
            stall_deadline_iso = self.stall_hard_deadline_at.isoformat()

        ch_pub = None
        if me and me.challenge:
            ch_pub = me.challenge.to_public_dict(now)

        return {
            "room_id": self.room_id,
            "phase": self.phase,
            "num_teams": self.num_teams,
            "teams": teams,
            "g": self.g,
            "cell_total": len(self.cells),
            "cells": list(self.cells),
            "tick_index": self.tick_index,
            "next_tick_at": self.next_tick_at.isoformat() if self.next_tick_at else None,
            "match_started_at": self.match_started_at.isoformat() if self.match_started_at else None,
            "match_end_at": self.match_end_at.isoformat() if self.match_end_at else None,
            "match_id": self.match_id,
            "finish_reason": self.finish_reason,
            "winning_team_ids": list(self.winning_team_ids),
            "scores": dict(self.scores),
            "players": {
                u: {
                    "username": s.username,
                    "team_id": s.team_id,
                    "role": s.role,
                    "ready": s.ready,
                    "connected": s.connected,
                    "paint": s.paint,
                    "personal_cells": s.personal_cells,
                }
                for u, s in self.players.items()
            },
            "me": {
                "username": viewer,
                "team_id": me.team_id if me else None,
                "role": me.role if me else None,
                "ready": me.ready if me else None,
                "paint": me.paint if me else None,
                "spectator_queue_position": (self.spectator_queue_next.index(viewer) + 1)
                if viewer in self.spectator_queue_next
                else None,
            },
            "opponent_ink": opp_ink,
            "stall": {"phase": self.stall_phase, "deadline_at": stall_deadline_iso},
            "hud_ink_poll_sec": p.hud_ink_poll_sec,
            "challenge": ch_pub,
            "config": {
                "paint_max": p.paint_max,
                "tick_ms": p.tick_ms,
                "diamond_cost": p.diamond_cost,
                "bundle": p.bundle,
                "max_buys_per_match": p.max_buys_per_match,
                "challenge_cooldown_sec": p.challenge_cooldown_sec,
                "debug_solo_lobby": bool(
                    settings.team_territory_debug_solo_lobby and settings.gamehub_env != "production"
                ),
            },
            "ready_deadline_at": self.ready_deadline_at.isoformat() if self.ready_deadline_at else None,
        }


def opponent_ink_snapshot(room: TerritoryRoom, viewer: str) -> dict[str, Any]:
    me = room.players.get(viewer)
    if not me:
        return {"sum": 0, "by_team": {}}
    by_team: dict[int, int] = {}
    s = 0
    for pl in room.players.values():
        if pl.username == viewer or pl.team_id == me.team_id:
            continue
        by_team[pl.team_id] = by_team.get(pl.team_id, 0) + pl.paint
        s += pl.paint
    return {"sum": s, "by_team": {str(k): v for k, v in sorted(by_team.items())}}


def add_player(
    room: TerritoryRoom,
    username: str,
    *,
    role: str,
    now: datetime,
) -> PlayerSlot:
    if username in room.players:
        pl = room.players[username]
        pl.connected = True
        return pl
    room.join_seq += 1
    tid = assign_team_id(room.join_seq, room.num_teams)
    pl = PlayerSlot(username=username, team_id=tid, role=role, join_order=room.join_seq)
    room.players[username] = pl
    p = room.params()
    if room.phase == "lobby" and room.ready_deadline_at is None:
        room.ready_deadline_at = now + timedelta(seconds=p.ready_timeout_sec)
    return pl


def start_challenge_if_allowed(
    room: TerritoryRoom,
    username: str,
    now: datetime,
    words: list[str],
) -> tuple[ChallengeSession | None, str | None]:
    if room.phase != "playing":
        return None, "not_playing"
    pl = room.players.get(username)
    if not pl or pl.role != "player":
        return None, "not_player"
    if pl.challenge is not None:
        return None, "already_active"
    p = room.params()
    if pl.challenges_started_match >= p.challenge_max_per_match:
        return None, "max_challenges"
    if pl.last_challenge_started_at:
        if now < pl.last_challenge_started_at + timedelta(seconds=p.challenge_cooldown_sec):
            return None, "cooldown"
    mode = pick_mode(p, random.Random(secrets.randbits(64)))
    sid = str(uuid.uuid4())
    sess = ChallengeSession(
        challenge_id=sid,
        username=username,
        mode=mode,  # type: ignore[arg-type]
        params=p,
        started_at_utc=now,
        words=list(words) if mode == 2 else [],
    )
    sess.start_round(now)
    pl.challenge = sess
    pl.challenges_started_match += 1
    pl.last_challenge_started_at = now
    room.touch_activity(now)
    return sess, None


def handle_challenge_answer(
    room: TerritoryRoom,
    username: str,
    now: datetime,
    answer: str | None,
    seq_label: int | None,
) -> tuple[dict[str, Any] | None, str | None]:
    pl = room.players.get(username)
    if not pl or not pl.challenge:
        return None, "no_session"
    sess = pl.challenge
    p = sess.params
    if sess.next_round_not_before and now < sess.next_round_not_before:
        return None, "round_gap"

    result: dict[str, Any] = {"round": sess.round_index, "paint_awarded": 0, "success": False}

    def advance_session_after_round() -> None:
        sess.after_round_gap(now)
        if sess.round_index >= p.challenge_problems:
            pl.challenge = None
            result["session_done"] = True
        else:
            sess.round_index += 1
            sess.start_round(now)
            result["session_done"] = False

    if sess.mode in (1, 2):
        timed_out = bool(sess.round_deadline_at and now > sess.round_deadline_at)
        if timed_out:
            ok = False
        else:
            ok = bool(
                answer is not None
                and sess.current_answer is not None
                and answer.strip().lower() == str(sess.current_answer).strip().lower()
            )
        if ok and pl.paint < p.paint_max:
            pl.paint += 1
            result["paint_awarded"] = 1
        result["success"] = ok
        advance_session_after_round()
        room.touch_activity(now)
        return result, None

    # mode 3 — последовательность 1…10
    timed_out = bool(sess.round_deadline_at and now > sess.round_deadline_at)
    if timed_out:
        result["success"] = False
        advance_session_after_round()
        room.touch_activity(now)
        return result, None

    if seq_label is None or int(seq_label) != sess.sequence_next:
        result["success"] = False
        advance_session_after_round()
        room.touch_activity(now)
        return result, None

    sess.sequence_next += 1
    if sess.sequence_next > 10:
        if pl.paint < p.paint_max:
            pl.paint += 1
            result["paint_awarded"] = 1
        result["success"] = True
        advance_session_after_round()
        room.touch_activity(now)
        return result, None

    result["success"] = True
    result["session_done"] = False
    room.touch_activity(now)
    return result, None
