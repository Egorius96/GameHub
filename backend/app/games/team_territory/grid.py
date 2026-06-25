"""Размер поля G×G от числа игроков P (п. 4.1 GAME_RULES)."""

from __future__ import annotations

from app.games.team_territory.constants import TeamTerritoryParams


def grid_size_from_P(p: int, params: TeamTerritoryParams) -> int:
    """P — число игроков в матче на старте (только role=player)."""
    if p <= 2:
        g = 8
    elif p <= 8:
        g = 10
    elif p <= 12:
        g = 12
    elif p <= 16:
        g = 14
    else:
        g = params.max_grid_g
    return min(g, params.max_grid_g)


def cell_total(g: int) -> int:
    return g * g


def rc_to_index(row: int, col: int, g: int) -> int:
    return row * g + col


def index_to_rc(index: int, g: int) -> tuple[int, int]:
    return index // g, index % g


def global_cap_scaled(params: TeamTerritoryParams, cell_total: int) -> int:
    """П. 4.1: масштабировать потолок закрасок за тик от площади."""
    factor = max(1, cell_total // 100)
    return params.global_cap_base * factor


def cap_c_for_tick(params: TeamTerritoryParams, cell_total: int, active_player_count: int) -> int:
    """C = min(GLOBAL_CAP_scaled, f(n)), п. 6.3."""
    gcap = global_cap_scaled(params, cell_total)
    n = max(0, active_player_count)
    f_n = params.f_n_offset + (n // params.f_n_divisor)
    return min(gcap, f_n)
