"""Debug-хелперы Team Territory (solo-лобби, тест начисления алмазов). Только dev."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from app.games.team_territory.room_engine import PlayerSlot, TerritoryRoom

logger = logging.getLogger(__name__)

# Первый ряд сетки (индексы 0, 1, 2) — секретный триггер победы в debug.
DEBUG_ROW1_CHEAT_CELLS = frozenset({0, 1, 2})


def team_territory_debug_solo_active() -> bool:
    return settings.team_territory_debug_solo_lobby and settings.gamehub_env != "production"


def ensure_debug_phantom_team_for_rewards(room: TerritoryRoom) -> None:
    """Для solo-debug: фиктивная вторая команда, чтобы match_rewards_allowed прошёл проверку ≥2 команд."""
    if not team_territory_debug_solo_active():
        return
    active = [t for t, n in room.match_team_sizes.items() if n > 0]
    if len(active) >= 2:
        return
    if not active:
        return
    player_team = active[0]
    for tid in range(room.num_teams):
        if tid != player_team:
            room.match_team_sizes[tid] = room.match_team_sizes.get(tid, 0) + 1
            logger.info(
                "team_territory_reward: debug phantom team added room=%s match_id=%s sizes=%s",
                room.room_id,
                room.match_id,
                dict(room.match_team_sizes),
            )
            return


def try_debug_row1_cheat_finish(room: TerritoryRoom, username: str, cell: int, now: datetime) -> bool:
    """После заявок на клетки 0, 1, 2 — мгновенная победа как при time_up (для теста 💎)."""
    if not team_territory_debug_solo_active():
        return False
    if room.phase != "playing" or cell not in DEBUG_ROW1_CHEAT_CELLS:
        return False
    pl: PlayerSlot | None = room.players.get(username)
    if pl is None or pl.role != "player":
        return False

    claims = room.debug_cheat_claims.setdefault(username, set())
    claims.add(cell)
    logger.info(
        "team_territory_reward: debug cheat claim room=%s user=%s cell=%s claims=%s",
        room.room_id,
        username,
        cell,
        sorted(claims),
    )
    if claims != DEBUG_ROW1_CHEAT_CELLS:
        return False

    p = room.params()
    for c in DEBUG_ROW1_CHEAT_CELLS:
        if 0 <= c < len(room.cells) and room.cells[c] == -1:
            pl.personal_cells += 1
        if 0 <= c < len(room.cells):
            room.cells[c] = pl.team_id

    pl.ticks_in_match = max(pl.ticks_in_match, p.min_ticks_for_reward)
    pl.claim_cell = None
    pl.claim_submitted = False
    ensure_debug_phantom_team_for_rewards(room)
    room._finish_match(now, "time_up")
    logger.info(
        "team_territory_reward: debug cheat finish room=%s match_id=%s user=%s team=%s "
        "ticks=%s winners=%s finish_reason=%s match_team_sizes=%s",
        room.room_id,
        room.match_id,
        username,
        pl.team_id,
        pl.ticks_in_match,
        list(room.winning_team_ids),
        room.finish_reason,
        dict(room.match_team_sizes),
    )
    return True
