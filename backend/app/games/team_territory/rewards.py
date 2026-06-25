"""Награды алмазами за матч Team Territory (п. 8–9 GAME_RULES)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from app.core.config import settings
from app.core.gameshub import ensure_gameshub_schema
from app.db.models import GameHubUser
from app.db.session import _session_factory
from app.games.team_territory.constants import TeamTerritoryParams, tt_params

if TYPE_CHECKING:
    from app.games.team_territory.room_engine import PlayerSlot, TerritoryRoom

from app.integrations.users_api import assign_user_other_data, sync_diamonds_to_sessions

logger = logging.getLogger(__name__)

MatchRewardKind = Literal["stale_idle", "none", "win", "loss", "tie"]

NO_DIAMOND_FINISH_REASONS = frozenset({"stale_idle", "opponent_left", "one_sided_idle"})


def teams_in_match(room: TerritoryRoom) -> set[int]:
    """Команды, у которых был хотя бы один игрок в стартовом составе матча."""
    return {t for t, n in room.match_team_sizes.items() if n > 0}


def teams_with_reward_ticks(room: TerritoryRoom, p: TeamTerritoryParams | None = None) -> set[int]:
    """Команды, у которых хотя бы один игрок набрал min_ticks_for_reward."""
    p = p or tt_params()
    out: set[int] = set()
    for pl in room.players.values():
        if pl.role != "player":
            continue
        if pl.ticks_in_match >= p.min_ticks_for_reward:
            out.add(pl.team_id)
    return out


def match_rewards_allowed(room: TerritoryRoom, p: TeamTerritoryParams | None = None) -> bool:
    """Награды разрешены, если матч честный (≥2 команд в составе, не void-finish)."""
    p = p or tt_params()
    if (room.finish_reason or "") in NO_DIAMOND_FINISH_REASONS:
        return False
    return len(teams_in_match(room)) >= 2


def match_rewards_block_reason(room: TerritoryRoom, p: TeamTerritoryParams | None = None) -> str | None:
    """Код причины отказа в наградах (для UI / логов)."""
    p = p or tt_params()
    reason = room.finish_reason or ""
    if reason in NO_DIAMOND_FINISH_REASONS:
        return reason
    if len(teams_in_match(room)) < 2:
        return "solo_match"
    return None


def player_match_reward_kind(
    room: TerritoryRoom,
    pl: PlayerSlot,
    p: TeamTerritoryParams | None = None,
) -> MatchRewardKind:
    p = p or tt_params()
    if (room.finish_reason or "") in NO_DIAMOND_FINISH_REASONS:
        return "stale_idle"
    if not match_rewards_allowed(room, p):
        return "none"
    if pl.role != "player" or pl.ticks_in_match < p.min_ticks_for_reward:
        return "none"
    winners = set(room.winning_team_ids or [])
    if len(winners) > 1:
        return "tie"
    if pl.team_id in winners:
        return "win"
    return "loss"


def player_match_reward_diamonds(
    room: TerritoryRoom,
    pl: PlayerSlot,
    p: TeamTerritoryParams | None = None,
) -> int:
    p = p or tt_params()
    kind = player_match_reward_kind(room, pl, p)
    if kind == "stale_idle" or kind == "none":
        return 0
    if kind == "win":
        return p.win_diamonds
    if kind == "loss":
        return p.loss_diamonds
    return p.tie_diamonds


def grant_match_rewards(room: TerritoryRoom, memory_guard: set[str]) -> None:
    if not room.match_id:
        return
    done_key = f"grant:{room.match_id}"
    if done_key in memory_guard:
        return
    p = tt_params()
    block = match_rewards_block_reason(room, p)
    if block:
        logger.info(
            "team_territory match rewards skipped room=%s match_id=%s reason=%s",
            room.room_id,
            room.match_id,
            block,
        )
        memory_guard.add(done_key)
        return

    memory_guard.add(done_key)
    db = _session_factory()()
    try:
        for uname, pl in list(room.players.items()):
            if pl.role != "player":
                continue
            ukey = f"{room.match_id}:{uname}"
            if ukey in memory_guard:
                continue
            amount = player_match_reward_diamonds(room, pl, p)
            if amount <= 0:
                continue
            u = db.query(GameHubUser).filter(GameHubUser.username == uname).first()
            if u is None:
                continue
            other = ensure_gameshub_schema(u.other_data or {})
            games = other.setdefault("games", {})
            prog = games.setdefault(settings.team_territory_game_key, {})
            if not isinstance(prog, dict):
                prog = {}
                games[settings.team_territory_game_key] = prog
            mr = prog.setdefault("match_rewards", {})
            if not isinstance(mr, dict):
                mr = {}
                prog["match_rewards"] = mr
            if mr.get(room.match_id):
                memory_guard.add(ukey)
                continue
            cur = int(other.get("diamonds", 0))
            other["diamonds"] = cur + amount
            mr[room.match_id] = amount
            if len(mr) > 80:
                for k in list(mr.keys())[:40]:
                    mr.pop(k, None)
            assign_user_other_data(u, other)
            db.commit()
            memory_guard.add(ukey)
            sync_diamonds_to_sessions(uname, int(other["diamonds"]))
            logger.info(
                "team_territory match reward granted user=%s match_id=%s amount=%d",
                uname,
                room.match_id,
                amount,
            )
    except Exception:
        logger.exception(
            "team_territory match rewards failed room=%s match_id=%s",
            room.room_id,
            room.match_id,
        )
        db.rollback()
        memory_guard.discard(done_key)
    finally:
        db.close()
