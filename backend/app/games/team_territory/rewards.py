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


def _player_reward_skip_reason(
    room: TerritoryRoom,
    pl: PlayerSlot,
    p: TeamTerritoryParams,
) -> str | None:
    if pl.role != "player":
        return f"role={pl.role}"
    kind = player_match_reward_kind(room, pl, p)
    if kind in ("none", "stale_idle"):
        if (room.finish_reason or "") in NO_DIAMOND_FINISH_REASONS:
            return f"void_finish={room.finish_reason}"
        if not match_rewards_allowed(room, p):
            return f"rewards_blocked={match_rewards_block_reason(room, p)}"
        if pl.ticks_in_match < p.min_ticks_for_reward:
            return f"ticks={pl.ticks_in_match}<{p.min_ticks_for_reward}"
        winners = set(room.winning_team_ids or [])
        if pl.team_id not in winners and len(winners) == 1:
            return f"not_winner team={pl.team_id} winners={sorted(winners)}"
        return f"kind={kind}"
    return None


def grant_match_rewards(room: TerritoryRoom, memory_guard: set[str]) -> None:
    if not room.match_id:
        logger.warning(
            "team_territory_reward: grant aborted — no match_id room=%s phase=%s",
            room.room_id,
            room.phase,
        )
        return
    done_key = f"grant:{room.match_id}"
    if done_key in memory_guard:
        logger.debug(
            "team_territory_reward: grant already done (memory) room=%s match_id=%s",
            room.room_id,
            room.match_id,
        )
        return

    p = tt_params()
    players_summary = [
        {
            "user": u,
            "role": pl.role,
            "team": pl.team_id,
            "ticks": pl.ticks_in_match,
            "kind": player_match_reward_kind(room, pl, p),
            "diamonds": player_match_reward_diamonds(room, pl, p),
        }
        for u, pl in room.players.items()
    ]
    logger.info(
        "team_territory_reward: grant start room=%s match_id=%s finish_reason=%s "
        "winners=%s match_team_sizes=%s min_ticks=%s win_diamonds=%s players=%s",
        room.room_id,
        room.match_id,
        room.finish_reason,
        list(room.winning_team_ids),
        dict(room.match_team_sizes),
        p.min_ticks_for_reward,
        p.win_diamonds,
        players_summary,
    )

    block = match_rewards_block_reason(room, p)
    if block:
        logger.info(
            "team_territory_reward: grant skipped room=%s match_id=%s block=%s "
            "teams_in_match=%s finish_reason=%s",
            room.room_id,
            room.match_id,
            block,
            sorted(teams_in_match(room)),
            room.finish_reason,
        )
        memory_guard.add(done_key)
        return

    memory_guard.add(done_key)
    db = _session_factory()()
    granted = 0
    try:
        for uname, pl in list(room.players.items()):
            if pl.role != "player":
                logger.info(
                    "team_territory_reward: skip user=%s reason=role_%s",
                    uname,
                    pl.role,
                )
                continue
            ukey = f"{room.match_id}:{uname}"
            if ukey in memory_guard:
                logger.info(
                    "team_territory_reward: skip user=%s reason=already_granted_memory",
                    uname,
                )
                continue
            amount = player_match_reward_diamonds(room, pl, p)
            kind = player_match_reward_kind(room, pl, p)
            if amount <= 0:
                skip = _player_reward_skip_reason(room, pl, p)
                logger.info(
                    "team_territory_reward: skip user=%s amount=0 kind=%s reason=%s "
                    "ticks=%s team=%s winners=%s",
                    uname,
                    kind,
                    skip,
                    pl.ticks_in_match,
                    pl.team_id,
                    list(room.winning_team_ids),
                )
                continue
            u = db.query(GameHubUser).filter(GameHubUser.username == uname).first()
            if u is None:
                logger.warning(
                    "team_territory_reward: skip user=%s reason=not_in_gamehub_users",
                    uname,
                )
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
            prev_mr = mr.get(room.match_id)
            if prev_mr:
                logger.info(
                    "team_territory_reward: skip user=%s reason=already_in_match_rewards amount=%s",
                    uname,
                    prev_mr,
                )
                memory_guard.add(ukey)
                continue
            cur = int(other.get("diamonds", 0))
            new_bal = cur + amount
            other["diamonds"] = new_bal
            mr[room.match_id] = amount
            if len(mr) > 80:
                for k in list(mr.keys())[:40]:
                    mr.pop(k, None)
            logger.info(
                "team_territory_reward: committing user=%s match_id=%s kind=%s "
                "amount=%d balance_before=%d balance_after=%d",
                uname,
                room.match_id,
                kind,
                amount,
                cur,
                new_bal,
            )
            assign_user_other_data(u, other)
            db.commit()
            memory_guard.add(ukey)
            sync_diamonds_to_sessions(uname, new_bal)
            granted += 1
            logger.info(
                "team_territory_reward: granted user=%s match_id=%s kind=%s amount=%d balance=%d",
                uname,
                room.match_id,
                kind,
                amount,
                new_bal,
            )
        if granted == 0:
            logger.warning(
                "team_territory_reward: grant finished with 0 payouts room=%s match_id=%s",
                room.room_id,
                room.match_id,
            )
        else:
            logger.info(
                "team_territory_reward: grant complete room=%s match_id=%s granted_count=%d",
                room.room_id,
                room.match_id,
                granted,
            )
    except Exception:
        logger.exception(
            "team_territory_reward: grant failed room=%s match_id=%s granted_so_far=%d",
            room.room_id,
            room.match_id,
            granted,
        )
        db.rollback()
        memory_guard.discard(done_key)
    finally:
        db.close()
