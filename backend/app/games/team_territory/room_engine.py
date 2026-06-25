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
from app.games.team_territory.combos import register_new_combos, register_new_line_combos
from app.games.team_territory.constants import TeamTerritoryParams, tt_params
from app.games.team_territory.debug import ensure_debug_phantom_team_for_rewards, team_territory_debug_solo_active
from app.games.team_territory.grid import cap_c_for_tick, cell_total, grid_size_from_P
from app.games.team_territory.rewards import player_match_reward_diamonds, player_match_reward_kind, match_rewards_block_reason
from app.games.team_territory.teams import (
    MAX_PLAYERS_IN_LOBBY,
    MAX_PLAYERS_PER_TEAM,
    TEAM_COLORS,
    teams_public_meta,
)

TEAM_UNASSIGNED = -1


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def claim_paint_cost(room: TerritoryRoom, cell: int, team_id: int) -> int | None:
    """Стоимость заявки: 1 на нейтральную, repaint_cost на чужую. None — заявка недопустима."""
    if not (0 <= cell < len(room.cells)):
        return None
    if cell in room.combo_cells:
        return None
    owner = room.cells[cell]
    if owner == -1:
        return 1
    if owner == team_id:
        return None
    if owner >= 0:
        return room.params().repaint_cost
    return None


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

    def in_lobby_team(self) -> bool:
        return self.role == "player" and self.connected and self.team_id >= 0


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
    combo_counts: dict[int, int] = field(default_factory=dict)
    combo_bonus: dict[int, int] = field(default_factory=dict)
    line_combo_counts: dict[int, int] = field(default_factory=dict)
    line_combo_bonus: dict[int, int] = field(default_factory=dict)
    balance_bonus: dict[int, int] = field(default_factory=dict)
    final_scores: dict[int, int] = field(default_factory=dict)
    match_team_sizes: dict[int, int] = field(default_factory=dict)
    completed_triples: set[tuple[int, int, int]] = field(default_factory=set)
    completed_lines: set[tuple[str, int]] = field(default_factory=set)
    combo_cells: set[int] = field(default_factory=set)
    line_combo_cells: set[int] = field(default_factory=set)
    combo_center_cells: set[int] = field(default_factory=set)
    ready_deadline_at: datetime | None = None
    lobby_idle_since: datetime | None = None
    invite_cooldown_until: datetime | None = None
    invite_broadcast_until: datetime | None = None
    invite_broadcast_by: str | None = None
    insufficient_teams_online_since: datetime | None = None
    team_last_activity_at: dict[int, datetime] = field(default_factory=dict)
    debug_cheat_claims: dict[str, set[int]] = field(default_factory=dict)
    lobby_countdown_until: datetime | None = None
    lobby_countdown_paused: bool = False
    lobby_countdown_paused_remaining_sec: float = 0.0
    lobby_countdown_pause_reason: str | None = None
    lobby_countdown_pause_detail: dict[str, Any] = field(default_factory=dict)
    lobby_countdown_last_event: dict[str, Any] = field(default_factory=dict)
    join_seq: int = 0
    _rng: random.Random = field(default_factory=lambda: random.Random(secrets.randbits(128)))

    def params(self) -> TeamTerritoryParams:
        return tt_params()

    def lobby_team_player_counts(self) -> dict[int, int]:
        counts = {i: 0 for i in range(self.num_teams)}
        for pl in self.lobby_roster_players():
            if 0 <= pl.team_id < self.num_teams:
                counts[pl.team_id] += 1
        return counts

    def lobby_roster_players(self) -> list[PlayerSlot]:
        """Игроки в лобби с явно выбранной командой и активным WS."""
        return [p for p in self.players.values() if p.in_lobby_team()]

    def lobby_connected_count(self) -> int:
        return sum(1 for p in self.active_players() if p.connected)

    def lobby_teams_imbalanced(self, *, max_diff: int = 2) -> bool:
        counts = list(self.lobby_team_player_counts().values())
        if not counts:
            return False
        return max(counts) - min(counts) >= max_diff

    def active_players(self) -> list[PlayerSlot]:
        return [p for p in self.players.values() if p.role == "player"]

    def ready_players(self) -> list[PlayerSlot]:
        return [p for p in self.lobby_roster_players() if p.ready]

    def teams_represented(self, plist: list[PlayerSlot]) -> set[int]:
        return {p.team_id for p in plist if p.team_id >= 0}

    def connected_teams_online(self) -> set[int]:
        out: set[int] = set()
        for pl in self.active_players():
            if not pl.connected:
                continue
            if 0 <= pl.team_id < self.num_teams:
                out.add(pl.team_id)
        return out

    def _track_insufficient_teams_online(self, now: datetime) -> None:
        if len(self.connected_teams_online()) >= 2:
            self.insufficient_teams_online_since = None
        elif self.insufficient_teams_online_since is None:
            self.insufficient_teams_online_since = now

    def maybe_finish_opponent_left(self, now: datetime) -> bool:
        """Досрочный финиш, если онлайн осталась одна команда дольше grace."""
        if self.phase != "playing":
            return False
        self._track_insufficient_teams_online(now)
        since = self.insufficient_teams_online_since
        if since is None:
            return False
        grace = self.params().opponent_left_grace_sec
        if (now - since).total_seconds() < grace:
            return False
        self._finish_match(now, "opponent_left")
        return True

    def _ready_meets_min_start(self, ready: list[PlayerSlot]) -> bool:
        """Минимум 2 готовых игрока в 2 разных командах (п. 3 GAME_RULES)."""
        p = self.params()
        if team_territory_debug_solo_active():
            return len(ready) >= 1
        if len(ready) < max(2, p.min_participants):
            return False
        return len(self.teams_represented(ready)) >= 2

    def can_start_match(self, now: datetime) -> bool:
        ready = self.ready_players()
        if len(ready) < 1:
            return False
        p = self.params()
        roster = self.lobby_roster_players()
        min_players = 1 if team_territory_debug_solo_active() else max(2, p.min_participants)
        if len(roster) < min_players:
            return False
        if not self._ready_meets_min_start(ready):
            return False
        if not team_territory_debug_solo_active() and self.lobby_teams_imbalanced():
            return False
        return all(pl.ready for pl in roster)

    def _lobby_min_players(self) -> int:
        p = self.params()
        return 1 if team_territory_debug_solo_active() else max(2, p.min_participants)

    def _team_meta(self, team_id: int) -> dict[str, Any]:
        if 0 <= team_id < len(TEAM_COLORS):
            t = TEAM_COLORS[team_id]
            return {"team_id": team_id, "key": t["key"], "name": t["name"]}
        return {"team_id": team_id, "key": str(team_id), "name": str(team_id)}

    def lobby_countdown_active(self) -> bool:
        return self.lobby_countdown_until is not None or self.lobby_countdown_paused

    def clear_lobby_countdown(self) -> None:
        self.lobby_countdown_until = None
        self.lobby_countdown_paused = False
        self.lobby_countdown_paused_remaining_sec = 0.0
        self.lobby_countdown_pause_reason = None
        self.lobby_countdown_pause_detail = {}
        self.lobby_countdown_last_event = {}

    def begin_lobby_countdown(self, now: datetime) -> None:
        if not self.can_start_match(now):
            return
        sec = max(1, int(self.params().lobby_countdown_sec))
        self.lobby_countdown_until = now + timedelta(seconds=sec)
        self.lobby_countdown_paused = False
        self.lobby_countdown_paused_remaining_sec = float(sec)
        self.lobby_countdown_pause_reason = None
        self.lobby_countdown_pause_detail = {}

    def pause_lobby_countdown(self, now: datetime, reason: str, detail: dict[str, Any]) -> None:
        if self.lobby_countdown_until is not None and not self.lobby_countdown_paused:
            self.lobby_countdown_paused_remaining_sec = max(
                0.0, (self.lobby_countdown_until - now).total_seconds()
            )
        self.lobby_countdown_until = None
        self.lobby_countdown_paused = True
        self.lobby_countdown_pause_reason = reason
        merged = dict(detail)
        if self.lobby_countdown_last_event:
            merged["last_event"] = dict(self.lobby_countdown_last_event)
        self.lobby_countdown_pause_detail = merged

    def resume_lobby_countdown(self, now: datetime) -> None:
        if not self.can_start_match(now):
            return
        sec = max(0.5, float(self.lobby_countdown_paused_remaining_sec or self.params().lobby_countdown_sec))
        self.lobby_countdown_until = now + timedelta(seconds=sec)
        self.lobby_countdown_paused = False
        self.lobby_countdown_pause_reason = None
        self.lobby_countdown_pause_detail = {}

    def _lobby_countdown_failure(self) -> tuple[str, dict[str, Any]] | None:
        roster = self.lobby_roster_players()
        min_players = self._lobby_min_players()
        if len(roster) < min_players:
            return "not_enough_players", {
                "players": len(roster),
                "required": min_players,
            }
        if not team_territory_debug_solo_active() and self.lobby_teams_imbalanced():
            return "teams_imbalanced", {"counts": dict(self.lobby_team_player_counts())}
        not_ready = [p.username for p in roster if not p.ready]
        if not_ready:
            return "not_all_ready", {"waiting": not_ready}
        ready = self.ready_players()
        if not self._ready_meets_min_start(ready):
            return "not_enough_teams", {
                "teams_ready": len(self.teams_represented(ready)),
                "required_teams": 1 if team_territory_debug_solo_active() else 2,
            }
        return None

    def on_lobby_roster_changed(self, now: datetime, event: dict[str, Any] | None = None) -> None:
        if self.phase != "lobby":
            return
        if event:
            ev = dict(event)
            tid = ev.get("team_id")
            if isinstance(tid, int) and tid >= 0:
                ev["team"] = self._team_meta(tid)
            self.lobby_countdown_last_event = ev
        if not self.lobby_countdown_active():
            if self.can_start_match(now):
                self.begin_lobby_countdown(now)
            return
        if len(self.ready_players()) == 0:
            self.clear_lobby_countdown()
            return
        fail = self._lobby_countdown_failure()
        if fail is not None:
            reason, detail = fail
            self.pause_lobby_countdown(now, reason, detail)
            return
        if self.lobby_countdown_paused and self.can_start_match(now):
            self.resume_lobby_countdown(now)

    def tick_lobby_countdown(self, now: datetime) -> None:
        if self.phase != "lobby":
            return
        if not self.lobby_countdown_active():
            if self.can_start_match(now):
                self.begin_lobby_countdown(now)
            return
        if len(self.ready_players()) == 0:
            self.clear_lobby_countdown()
            return
        fail = self._lobby_countdown_failure()
        if fail is not None:
            if not self.lobby_countdown_paused:
                reason, detail = fail
                self.pause_lobby_countdown(now, reason, detail)
            return
        if self.lobby_countdown_paused:
            if self.can_start_match(now):
                self.resume_lobby_countdown(now)
            return
        if self.lobby_countdown_until and now >= self.lobby_countdown_until:
            self.clear_lobby_countdown()
            if self.can_start_match(now):
                self.start_match(now)

    def lobby_countdown_public(self, now: datetime) -> dict[str, Any]:
        if self.phase != "lobby" or not self.lobby_countdown_active():
            return {"active": False, "paused": False, "seconds_left": 0}
        seconds_left = 0.0
        if self.lobby_countdown_paused:
            seconds_left = float(self.lobby_countdown_paused_remaining_sec)
        elif self.lobby_countdown_until is not None:
            seconds_left = max(0.0, (self.lobby_countdown_until - now).total_seconds())
        return {
            "active": True,
            "paused": self.lobby_countdown_paused,
            "seconds_left": round(seconds_left, 1),
            "total_sec": int(self.params().lobby_countdown_sec),
            "until": self.lobby_countdown_until.isoformat() if self.lobby_countdown_until else None,
            "pause_reason": self.lobby_countdown_pause_reason,
            "pause_detail": dict(self.lobby_countdown_pause_detail),
        }

    def start_match(self, now: datetime) -> None:
        self.clear_lobby_countdown()
        p = self.params()
        participants = [x for x in self.lobby_roster_players() if x.ready]
        if not self._ready_meets_min_start(participants):
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
        self.combo_counts = {i: 0 for i in range(self.num_teams)}
        self.combo_bonus = {i: 0 for i in range(self.num_teams)}
        self.line_combo_counts = {i: 0 for i in range(self.num_teams)}
        self.line_combo_bonus = {i: 0 for i in range(self.num_teams)}
        self.balance_bonus = {i: 0 for i in range(self.num_teams)}
        self.final_scores = {i: 0 for i in range(self.num_teams)}
        self.match_team_sizes = {i: 0 for i in range(self.num_teams)}
        self.completed_triples = set()
        self.completed_lines = set()
        self.combo_cells = set()
        self.line_combo_cells = set()
        self.combo_center_cells = set()
        self.insufficient_teams_online_since = None
        self.team_last_activity_at = {}
        self.debug_cheat_claims = {}
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
                self.match_team_sizes[pl.team_id] = self.match_team_sizes.get(pl.team_id, 0) + 1
            elif pl.role == "player":
                # не готов к старту — переводим в наблюдатели
                pl.role = "spectator"
                pl.ready = False
                pl.paint = 0
                pl.claim_cell = None
        ensure_debug_phantom_team_for_rewards(self)
        self._update_stall_deadlines(now)

    def lobby_idle_expired(self, now: datetime) -> bool:
        """П. 3: если долго нет условий для старта — закрыть лобби."""
        if self.phase != "lobby":
            return False
        p = self.params()
        if self.can_start_match(now):
            return False
        if len(self.active_players()) >= max(2, p.min_participants):
            ready = self.ready_players()
            if self._ready_meets_min_start(ready):
                return False
        anchor = self.lobby_idle_since or self.created_at
        return (now - anchor).total_seconds() >= p.lobby_idle_close_sec

    def reset_idle_lobby(self, now: datetime) -> None:
        self.clear_lobby_countdown()
        self.players.clear()
        self.spectator_queue_next.clear()
        self.ready_deadline_at = None
        self.lobby_idle_since = now
        self.created_at = now

    def touch_activity(self, now: datetime, *, team_id: int | None = None) -> None:
        self.last_significant_activity_at = now
        self.stall_phase = "none"
        if team_id is not None and 0 <= team_id < self.num_teams:
            self.team_last_activity_at[team_id] = now
        if self.phase == "playing":
            self._update_stall_deadlines(now)

    def teams_in_match(self) -> set[int]:
        return {t for t, n in self.match_team_sizes.items() if n > 0}

    def maybe_finish_one_sided_idle(self, now: datetime) -> bool:
        """Ничья, если 5+ минут действия только у одной команды."""
        if self.phase != "playing":
            return False
        teams = self.teams_in_match()
        if len(teams) < 2:
            return False
        window = self.params().one_sided_idle_sec
        active_in_window = {
            t
            for t in teams
            if (lat := self.team_last_activity_at.get(t)) is not None
            and (now - lat).total_seconds() < window
        }
        if len(active_in_window) != 1:
            return False
        only_team = next(iter(active_in_window))
        other_anchor: datetime | None = None
        for t in teams:
            if t == only_team:
                continue
            lat = self.team_last_activity_at.get(t)
            anchor = lat if lat is not None else self.match_started_at
            if anchor is None:
                continue
            if other_anchor is None or anchor > other_anchor:
                other_anchor = anchor
        if other_anchor is None:
            return False
        if (now - other_anchor).total_seconds() >= window:
            self._finish_match(now, "one_sided_idle")
            return True
        return False

    def _update_stall_deadlines(self, now: datetime) -> None:
        p = self.params()
        base = self.last_significant_activity_at or now
        self.stall_warn_deadline_at = base + timedelta(seconds=p.match_stall_idle_sec - p.match_stall_warn_before_sec)
        self.stall_hard_deadline_at = base + timedelta(seconds=p.match_stall_idle_sec)

    def maybe_finish_stall_or_timer(self, now: datetime) -> None:
        if self.phase != "playing":
            return
        if self.maybe_finish_opponent_left(now):
            return
        if self.maybe_finish_one_sided_idle(now):
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
        p = self.params()
        bonus_pts = max(0, int(p.combo_bonus_points))
        line_pts = max(0, int(p.line_combo_bonus_points))
        sizes = self.match_team_sizes or {i: 0 for i in range(self.num_teams)}
        active_sizes = [c for c in sizes.values() if c > 0]
        max_size = max(active_sizes) if active_sizes else 1
        for t in range(self.num_teams):
            territory = sum(1 for c in self.cells if c == t)
            combo = self.combo_counts.get(t, 0) * bonus_pts
            line_combo = self.line_combo_counts.get(t, 0) * line_pts
            team_size = sizes.get(t, 0)
            balance = 0
            if team_size > 0 and team_size < max_size:
                balance = int(round(territory * (max_size / team_size - 1)))
            self.scores[t] = territory
            self.combo_bonus[t] = combo
            self.line_combo_bonus[t] = line_combo
            self.balance_bonus[t] = balance
            self.final_scores[t] = territory + combo + line_combo + balance
        best = max(self.final_scores.values()) if self.final_scores else 0
        self.winning_team_ids = [tid for tid, sc in self.final_scores.items() if sc == best and best > 0]
        if reason in ("stale_idle", "opponent_left", "one_sided_idle"):
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
            cost = claim_paint_cost(self, cell, pl.team_id)
            if cost is None or pl.paint < cost:
                continue
            raw.append(
                {
                    "username": pl.username,
                    "cell": cell,
                    "team_id": pl.team_id,
                    "personal_cells": pl.personal_cells,
                    "paint_cost": cost,
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

        painted: list[int] = []
        for w in winners:
            pl = self.players.get(w["username"])
            if pl is None:
                continue
            cell = w["cell"]
            cost = int(w.get("paint_cost") or claim_paint_cost(self, cell, pl.team_id) or 0)
            if cost <= 0 or claim_paint_cost(self, cell, pl.team_id) is None or pl.paint < cost:
                continue
            self.cells[cell] = pl.team_id
            pl.paint -= cost
            pl.personal_cells += 1
            painted.append(cell)

        if painted:
            register_new_combos(
                self.cells,
                self.g,
                painted,
                self.completed_triples,
                self.combo_counts,
                self.combo_cells,
                self.combo_center_cells,
            )
            register_new_line_combos(
                self.cells,
                self.g,
                painted,
                self.completed_lines,
                self.line_combo_counts,
                self.line_combo_cells,
                self.combo_cells,
            )

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
        self.clear_lobby_countdown()
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
        self.combo_counts = {}
        self.combo_bonus = {}
        self.line_combo_counts = {}
        self.line_combo_bonus = {}
        self.balance_bonus = {}
        self.final_scores = {}
        self.match_team_sizes = {}
        self.completed_triples = set()
        self.completed_lines = set()
        self.combo_cells = set()
        self.line_combo_cells = set()
        self.combo_center_cells = set()
        self.stall_phase = "none"
        self.stall_warn_deadline_at = None
        self.stall_hard_deadline_at = None
        self.last_significant_activity_at = None
        self.insufficient_teams_online_since = None
        self.team_last_activity_at = {}
        self.debug_cheat_claims = {}
        self.lobby_idle_since = now
        for u in list(self.spectator_queue_next):
            pl = self.players.get(u)
            if pl and pl.role == "spectator":
                pl.role = "player"
        self.spectator_queue_next.clear()
        for pl in self.players.values():
            pl.ready = False
            pl.claim_cell = None
            pl.paint = 0
        self.ready_deadline_at = None

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

        challenge_cooldown_until = None
        if me and me.last_challenge_started_at:
            until = me.last_challenge_started_at + timedelta(seconds=p.challenge_cooldown_sec)
            if until > now:
                challenge_cooldown_until = until.isoformat()

        me_reward_kind = None
        me_reward_diamonds = None
        me_rewards_block = None
        if self.phase == "finished" and me:
            me_reward_kind = player_match_reward_kind(self, me, p)
            me_reward_diamonds = player_match_reward_diamonds(self, me, p)
            if me_reward_kind == "none":
                me_rewards_block = match_rewards_block_reason(self, p)
                if me_rewards_block is None and me.ticks_in_match < p.min_ticks_for_reward:
                    me_rewards_block = "insufficient_ticks"

        tick_closes_in_ms = (
            max(0, int((self.next_tick_at - now).total_seconds() * 1000)) if self.next_tick_at else None
        )

        return {
            "room_id": self.room_id,
            "phase": self.phase,
            "num_teams": self.num_teams,
            "teams": teams,
            "g": self.g,
            "cell_total": len(self.cells),
            "cells": list(self.cells),
            "tick_index": self.tick_index,
            "server_now": now.isoformat(),
            "tick_closes_in_ms": tick_closes_in_ms,
            "next_tick_at": self.next_tick_at.isoformat() if self.next_tick_at else None,
            "match_started_at": self.match_started_at.isoformat() if self.match_started_at else None,
            "match_end_at": self.match_end_at.isoformat() if self.match_end_at else None,
            "match_id": self.match_id,
            "finish_reason": self.finish_reason,
            "winning_team_ids": list(self.winning_team_ids),
            "scores": dict(self.scores),
            "combo_counts": {str(k): v for k, v in sorted(self.combo_counts.items())},
            "combo_bonus": {str(k): v for k, v in sorted(self.combo_bonus.items())},
            "line_combo_counts": {str(k): v for k, v in sorted(self.line_combo_counts.items())},
            "line_combo_bonus": {str(k): v for k, v in sorted(self.line_combo_bonus.items())},
            "balance_bonus": {str(k): v for k, v in sorted(self.balance_bonus.items())},
            "match_team_sizes": {str(k): v for k, v in sorted(self.match_team_sizes.items())},
            "lobby_teams_imbalanced": self.lobby_teams_imbalanced() if self.phase == "lobby" else False,
            "lobby_connected_count": self.lobby_connected_count() if self.phase == "lobby" else 0,
            "lobby_in_team_count": len(self.lobby_roster_players()) if self.phase == "lobby" else 0,
            "lobby_countdown": self.lobby_countdown_public(now),
            "final_scores": {str(k): v for k, v in sorted(self.final_scores.items())},
            "combo_cells": sorted(self.combo_cells),
            "line_combo_cells": sorted(self.line_combo_cells),
            "combo_center_cells": sorted(self.combo_center_cells),
            "tick_claims": tick_claims_snapshot(self),
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
                "claim_cell": me.claim_cell if me else None,
                "spectator_queue_position": (self.spectator_queue_next.index(viewer) + 1)
                if viewer in self.spectator_queue_next
                else None,
                "challenge_cooldown_until": challenge_cooldown_until,
                "next_regen_at": me.next_regen_at.isoformat() if me and me.next_regen_at else None,
                "match_reward_kind": me_reward_kind,
                "match_reward_diamonds": me_reward_diamonds,
                "match_rewards_block": me_rewards_block,
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
                "challenge_riddle_sec": p.challenge_riddle_sec,
                "challenge_math_sec": p.challenge_math_sec,
                "challenge_sequence_sec": p.challenge_sequence_sec,
                "combo_bonus_points": p.combo_bonus_points,
                "line_combo_bonus_points": p.line_combo_bonus_points,
                "repaint_cost": p.repaint_cost,
                "challenge_max_paint_start": p.challenge_max_paint_start,
                "regen_sec": p.regen_sec,
                "win_diamonds": p.win_diamonds,
                "loss_diamonds": p.loss_diamonds,
                "tie_diamonds": p.tie_diamonds,
                "min_ticks_for_reward": p.min_ticks_for_reward,
                "ready_timeout_sec": p.ready_timeout_sec,
                "lobby_countdown_sec": p.lobby_countdown_sec,
                "max_players_per_team": MAX_PLAYERS_PER_TEAM,
                "max_players_in_lobby": MAX_PLAYERS_IN_LOBBY,
                "debug_solo_lobby": team_territory_debug_solo_active(),
            },
            "ready_deadline_at": self.ready_deadline_at.isoformat() if self.ready_deadline_at else None,
            "invite_cooldown_until": (
                self.invite_cooldown_until.isoformat()
                if self.invite_cooldown_until and self.invite_cooldown_until > now
                else None
            ),
        }


def tick_claims_snapshot(room: TerritoryRoom) -> dict[str, list[int]]:
    """Заявки на клетки в текущем тике: cell -> уникальные team_id."""
    if room.phase != "playing":
        return {}
    by_cell: dict[int, set[int]] = {}
    for pl in room.active_players():
        if pl.claim_cell is None:
            continue
        cell = pl.claim_cell
        if claim_paint_cost(room, cell, pl.team_id) is None:
            continue
        by_cell.setdefault(cell, set()).add(pl.team_id)
    return {str(k): sorted(v) for k, v in sorted(by_cell.items())}


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


def default_team_id(room: TerritoryRoom) -> int:
    """Команда с наименьшим числом игроков в лобби (стартовый выбор)."""
    counts = {i: 0 for i in range(room.num_teams)}
    for pl in room.players.values():
        if pl.role == "player" and 0 <= pl.team_id < room.num_teams:
            counts[pl.team_id] = counts.get(pl.team_id, 0) + 1
    return min(counts.keys(), key=lambda tid: (counts[tid], tid))


def remove_lobby_player(room: TerritoryRoom, username: str) -> bool:
    """Убрать игрока из лобби (отключение / явный выход)."""
    if room.phase != "lobby":
        return False
    return room.players.pop(username, None) is not None


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
        if room.phase == "lobby" and pl.role == "player":
            pl.ready = False
        return pl
    room.join_seq += 1
    tid = TEAM_UNASSIGNED if room.phase == "lobby" and role == "player" else default_team_id(room)
    pl = PlayerSlot(username=username, team_id=tid, role=role, join_order=room.join_seq)
    room.players[username] = pl
    if room.phase == "lobby" and room.lobby_idle_since is None:
        room.lobby_idle_since = now
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
    if pl.last_challenge_started_at:
        if now < pl.last_challenge_started_at + timedelta(seconds=p.challenge_cooldown_sec):
            return None, "cooldown"
    if pl.paint > p.challenge_max_paint_start:
        return None, "too_much_paint"
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
    room.touch_activity(now, team_id=pl.team_id)
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
        room.touch_activity(now, team_id=pl.team_id)
        return result, None

    # mode 3 — последовательность 1…10
    timed_out = bool(sess.round_deadline_at and now > sess.round_deadline_at)
    if timed_out:
        result["success"] = False
        advance_session_after_round()
        room.touch_activity(now, team_id=pl.team_id)
        return result, None

    if seq_label is None or int(seq_label) != sess.sequence_next:
        result["success"] = False
        advance_session_after_round()
        room.touch_activity(now, team_id=pl.team_id)
        return result, None

    sess.sequence_next += 1
    if sess.sequence_layout is not None:
        sess.sequence_layout = [c for c in sess.sequence_layout if int(c.get("label", -1)) != int(seq_label)]
    if sess.sequence_next > 10:
        if pl.paint < p.paint_max:
            pl.paint += 1
            result["paint_awarded"] = 1
        result["success"] = True
        advance_session_after_round()
        room.touch_activity(now, team_id=pl.team_id)
        return result, None

    result["success"] = True
    result["session_done"] = False
    room.touch_activity(now, team_id=pl.team_id)
    return result, None
