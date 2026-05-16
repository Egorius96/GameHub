"""Юнит-тесты Team Territory: сетка и лимит C."""

import pytest

from app.games.team_territory.constants import TeamTerritoryParams
from app.games.team_territory.grid import cap_c_for_tick, cell_total, grid_size_from_P


@pytest.fixture
def p() -> TeamTerritoryParams:
    return TeamTerritoryParams(
        paint_max=10,
        tick_ms=6000,
        regen_sec=45,
        bundle=3,
        diamond_cost=2,
        max_buys_per_match=2,
        global_cap_base=12,
        f_n_divisor=3,
        f_n_offset=4,
        max_grid_g=18,
        match_max_sec=900,
        match_stall_idle_sec=300,
        match_stall_warn_before_sec=60,
        win_diamonds=5,
        ready_timeout_sec=60,
        min_participants=2,
        challenge_problems=5,
        challenge_riddle_sec=5,
        challenge_cooldown_sec=120,
        challenge_round_gap_sec=3,
        challenge_max_per_match=6,
        challenge_weight_math=0.34,
        challenge_weight_spelling=0.33,
        challenge_weight_sequence=0.33,
        challenge_spelling_wordlist="",
        hud_ink_poll_sec=2.5,
        min_ticks_for_reward=3,
        lobby_idle_close_sec=600,
    )


def test_grid_size_from_p_table(p: TeamTerritoryParams) -> None:
    assert grid_size_from_P(1, p) == 10
    assert grid_size_from_P(5, p) == 10
    assert grid_size_from_P(6, p) == 12
    assert grid_size_from_P(10, p) == 12
    assert grid_size_from_P(11, p) == 14
    assert grid_size_from_P(16, p) == 14
    assert grid_size_from_P(17, p) == 16
    assert grid_size_from_P(24, p) == 16
    assert grid_size_from_P(25, p) == 18
    assert grid_size_from_P(32, p) == 18


def test_cap_c_scales_with_cell_total(p: TeamTerritoryParams) -> None:
    g10 = cell_total(10)
    c10 = cap_c_for_tick(p, g10, 6)
    assert c10 == min(12, 4 + 6 // 3)  # 12 vs 6 -> 6
    g18 = cell_total(18)
    scaled_cap = 12 * max(1, g18 // 100)  # 12 * 3 = 36
    c18 = cap_c_for_tick(p, g18, 6)
    assert c18 == min(scaled_cap, 4 + 6 // 3)
