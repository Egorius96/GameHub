"""Параметры матча Team Territory (п. 12 GAME_RULES + п. 4.1 для G)."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class TeamTerritoryParams:
    paint_max: int
    tick_ms: int
    regen_sec: int
    bundle: int
    diamond_cost: int
    max_buys_per_match: int
    global_cap_base: int
    f_n_divisor: int
    f_n_offset: int
    max_grid_g: int
    match_max_sec: int
    match_stall_idle_sec: int
    match_stall_warn_before_sec: int
    win_diamonds: int
    loss_diamonds: int
    tie_diamonds: int
    ready_timeout_sec: int
    min_participants: int
    challenge_problems: int
    challenge_riddle_sec: int
    challenge_math_sec: int
    challenge_sequence_sec: int
    challenge_cooldown_sec: int
    challenge_max_paint_start: int
    challenge_round_gap_sec: int
    challenge_max_per_match: int
    challenge_weight_math: float
    challenge_weight_spelling: float
    challenge_weight_sequence: float
    challenge_spelling_wordlist: str
    hud_ink_poll_sec: float
    min_ticks_for_reward: int
    lobby_idle_close_sec: int
    combo_bonus_points: int
    repaint_cost: int
    opponent_left_grace_sec: int
    one_sided_idle_sec: int


def tt_params() -> TeamTerritoryParams:
    s = settings
    return TeamTerritoryParams(
        paint_max=int(s.tt_paint_max),
        tick_ms=int(s.tt_tick_ms),
        regen_sec=int(s.tt_regen_sec),
        bundle=int(s.tt_bundle),
        diamond_cost=int(s.tt_diamond_cost),
        max_buys_per_match=int(s.tt_max_buys_per_match),
        global_cap_base=int(s.tt_global_cap_base),
        f_n_divisor=max(1, int(s.tt_f_n_divisor)),
        f_n_offset=int(s.tt_f_n_offset),
        max_grid_g=int(s.tt_max_grid_g),
        match_max_sec=int(s.tt_match_max_sec),
        match_stall_idle_sec=int(s.tt_match_stall_idle_sec),
        match_stall_warn_before_sec=int(s.tt_match_stall_warn_before_sec),
        win_diamonds=int(s.tt_win_diamonds),
        loss_diamonds=int(s.tt_loss_diamonds),
        tie_diamonds=int(s.tt_tie_diamonds),
        ready_timeout_sec=int(s.tt_ready_timeout_sec),
        min_participants=int(s.tt_min_participants),
        challenge_problems=int(s.tt_challenge_problems),
        challenge_riddle_sec=int(s.tt_challenge_riddle_sec),
        challenge_math_sec=int(s.tt_challenge_math_sec),
        challenge_sequence_sec=int(s.tt_challenge_sequence_sec),
        challenge_cooldown_sec=int(s.tt_challenge_cooldown_sec),
        challenge_max_paint_start=int(s.tt_challenge_max_paint_start),
        challenge_round_gap_sec=int(s.tt_challenge_round_gap_sec),
        challenge_max_per_match=int(s.tt_challenge_max_per_match),
        challenge_weight_math=float(s.tt_challenge_weight_math),
        challenge_weight_spelling=float(s.tt_challenge_weight_spelling),
        challenge_weight_sequence=float(s.tt_challenge_weight_sequence),
        challenge_spelling_wordlist=str(s.tt_challenge_spelling_wordlist),
        hud_ink_poll_sec=float(s.tt_hud_ink_poll_sec),
        min_ticks_for_reward=int(s.tt_min_ticks_for_reward),
        lobby_idle_close_sec=int(s.tt_lobby_idle_close_sec),
        combo_bonus_points=int(s.tt_combo_bonus_points),
        repaint_cost=int(s.tt_repaint_cost),
        opponent_left_grace_sec=max(5, int(s.tt_opponent_left_grace_sec)),
        one_sided_idle_sec=max(60, int(s.tt_one_sided_idle_sec)),
    )
