"""Юнит-тесты Team Territory: сетка, лимит C, старт лобби."""

from datetime import datetime, timedelta, timezone

import pytest

from app.games.team_territory.constants import TeamTerritoryParams
from app.games.team_territory.grid import cap_c_for_tick, cell_total, grid_size_from_P
from app.games.team_territory.room_engine import PlayerSlot, TerritoryRoom, utcnow


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
        win_diamonds=50,
        loss_diamonds=10,
        tie_diamonds=10,
        ready_timeout_sec=60,
        min_participants=2,
        challenge_problems=5,
        challenge_riddle_sec=5,
        challenge_math_sec=7,
        challenge_sequence_sec=10,
        challenge_cooldown_sec=120,
        challenge_max_paint_start=5,
        challenge_round_gap_sec=3,
        challenge_max_per_match=6,
        challenge_weight_math=0.34,
        challenge_weight_spelling=0.33,
        challenge_weight_sequence=0.33,
        challenge_spelling_wordlist="",
        hud_ink_poll_sec=2.5,
        min_ticks_for_reward=3,
        lobby_idle_close_sec=600,
        combo_bonus_points=1,
        repaint_cost=2,
        opponent_left_grace_sec=60,
        one_sided_idle_sec=300,
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


def _room_with_players(usernames: list[str], *, ready: list[bool] | None = None) -> TerritoryRoom:
    room = TerritoryRoom(room_id="t", num_teams=2)
    now = utcnow()
    ready = ready if ready is not None else [True] * len(usernames)
    for i, u in enumerate(usernames):
        pl = PlayerSlot(username=u, team_id=i % 2, role="player", ready=ready[i], join_order=i + 1)
        room.players[u] = pl
    room.ready_deadline_at = now + timedelta(seconds=60)
    return room


def test_can_start_match_requires_two_ready_two_teams(p: TeamTerritoryParams) -> None:
    now = utcnow()
    solo = _room_with_players(["a"])
    assert solo.can_start_match(now) is False

    one_ready = _room_with_players(["a", "b"], ready=[True, False])
    assert one_ready.can_start_match(now) is False

    two_ready = _room_with_players(["a", "b"], ready=[True, True])
    assert two_ready._ready_meets_min_start(two_ready.ready_players()) is True
    assert two_ready.can_start_match(now) is True


def test_debug_solo_flag_allows_single_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import config

    monkeypatch.setattr(config.settings, "team_territory_debug_solo_lobby", True)
    monkeypatch.setattr(config.settings, "gamehub_env", "development")
    now = utcnow()
    solo = _room_with_players(["a"], ready=[True])
    assert solo.can_start_match(now) is True
    solo.start_match(now)
    assert solo.phase == "playing"
    assert solo.match_team_sizes.get(0, 0) >= 1
    assert solo.match_team_sizes.get(1, 0) >= 1


def test_lobby_roster_excludes_unassigned_and_disconnected() -> None:
    from app.games.team_territory.room_engine import TEAM_UNASSIGNED, add_player, remove_lobby_player

    room = TerritoryRoom(room_id="t", num_teams=4)
    now = utcnow()
    add_player(room, "online", role="player", now=now)
    room.players["online"].team_id = 1
    add_player(room, "ghost", role="player", now=now)
    room.players["ghost"].team_id = 2
    room.players["ghost"].connected = False
    add_player(room, "idle", role="player", now=now)
    assert room.players["idle"].team_id == TEAM_UNASSIGNED
    assert len(room.lobby_roster_players()) == 1
    assert room.lobby_roster_players()[0].username == "online"
    assert remove_lobby_player(room, "online") is True
    assert "online" not in room.players


def test_add_player_starts_unassigned_in_lobby() -> None:
    from app.games.team_territory.room_engine import TEAM_UNASSIGNED, add_player

    room = TerritoryRoom(room_id="t", num_teams=4)
    pl = add_player(room, "u", role="player", now=utcnow())
    assert pl.team_id == TEAM_UNASSIGNED


def test_debug_row1_cheat_finishes_with_win(monkeypatch: pytest.MonkeyPatch, p: TeamTerritoryParams) -> None:
    from app.core import config
    from app.games.team_territory.debug import try_debug_row1_cheat_finish
    from app.games.team_territory.rewards import match_rewards_allowed, player_match_reward_kind

    monkeypatch.setattr(config.settings, "team_territory_debug_solo_lobby", True)
    monkeypatch.setattr(config.settings, "gamehub_env", "development")
    room = _room_with_players(["a"], ready=[True])
    room.start_match(utcnow())
    pl = room.players["a"]
    now = utcnow()
    assert try_debug_row1_cheat_finish(room, "a", 0, now) is False
    assert try_debug_row1_cheat_finish(room, "a", 1, now) is False
    assert try_debug_row1_cheat_finish(room, "a", 2, now) is True
    assert room.phase == "finished"
    assert room.finish_reason == "time_up"
    assert pl.team_id in room.winning_team_ids
    assert match_rewards_allowed(room, p) is True
    assert player_match_reward_kind(room, pl, p) == "win"


def test_tick_claims_snapshot() -> None:
    from app.games.team_territory.room_engine import tick_claims_snapshot

    room = TerritoryRoom(room_id="t", num_teams=4)
    room.phase = "playing"
    room.g = 3
    room.cells = [-1] * 9
    room.players["a"] = PlayerSlot(username="a", team_id=0, role="player", claim_cell=4)
    room.players["b"] = PlayerSlot(username="b", team_id=2, role="player", claim_cell=4)
    room.players["c"] = PlayerSlot(username="c", team_id=1, role="player", claim_cell=1)
    snap = tick_claims_snapshot(room)
    assert snap == {"1": [1], "4": [0, 2]}


def test_start_match_only_includes_ready_players(p: TeamTerritoryParams) -> None:
    room = _room_with_players(["a", "b", "c"], ready=[True, True, False])
    room.start_match(utcnow())
    assert room.phase == "playing"
    assert room.players["c"].role == "spectator"
    assert len([x for x in room.active_players() if x.ready]) == 2


def test_process_tick_paints_neutral_cell(p: TeamTerritoryParams) -> None:
    room = _room_with_players(["a", "b"], ready=[True, True])
    room.start_match(utcnow())
    pl = room.players["a"]
    pl.claim_cell = 0
    pl.claim_submitted = True
    pl.paint = 5
    room.next_tick_at = utcnow() - timedelta(seconds=1)
    log = room.process_tick(utcnow())
    assert log.get("applied") is True
    assert room.cells[0] == pl.team_id
    assert pl.paint == 4


def test_process_tick_repaints_enemy_cell(p: TeamTerritoryParams) -> None:
    room = _room_with_players(["a", "b"], ready=[True, True])
    room.start_match(utcnow())
    room.cells[5] = 1
    pl = room.players["a"]
    assert pl.team_id != 1
    pl.claim_cell = 5
    pl.claim_submitted = True
    pl.paint = 5
    room.next_tick_at = utcnow() - timedelta(seconds=1)
    room.process_tick(utcnow())
    assert room.cells[5] == pl.team_id
    assert pl.paint == 3


def test_repaint_combo_cell_rejected(p: TeamTerritoryParams) -> None:
    room = _room_with_players(["a", "b"], ready=[True, True])
    room.start_match(utcnow())
    room.cells[5] = 1
    room.combo_cells.add(5)
    pl = room.players["a"]
    pl.claim_cell = 5
    pl.claim_submitted = True
    pl.paint = 5
    room.next_tick_at = utcnow() - timedelta(seconds=1)
    room.process_tick(utcnow())
    assert room.cells[5] == 1
    assert pl.paint == 5


def test_lobby_idle_expired_clears_when_no_min_players(p: TeamTerritoryParams) -> None:
    room = TerritoryRoom(room_id="idle", num_teams=2)
    room.lobby_idle_since = datetime.now(timezone.utc) - timedelta(seconds=700)
    room.players["solo"] = PlayerSlot(username="solo", team_id=0, role="player")
    assert room.lobby_idle_expired(utcnow()) is True
    room.reset_idle_lobby(utcnow())
    assert not room.players


def test_math_subtraction_never_negative() -> None:
    import random

    from app.games.team_territory.challenge import generate_math_problem

    rng = random.Random(42)
    for _ in range(200):
        expr, ans = generate_math_problem(rng)
        if " - " in expr:
            assert ans >= 0


def test_sequence_removes_tapped_circle() -> None:
    import random

    from app.games.team_territory.challenge import ChallengeSession, generate_sequence_layout
    from app.games.team_territory.constants import tt_params

    p = tt_params()
    sess = ChallengeSession(
        challenge_id="t",
        username="u",
        mode=3,
        params=p,
        started_at_utc=utcnow(),
    )
    sess.sequence_layout = generate_sequence_layout(random.Random(1))
    sess.sequence_next = 1
    before = len(sess.sequence_layout)
    label = sess.sequence_next
    sess.sequence_layout = [c for c in sess.sequence_layout if int(c.get("label", -1)) != label]
    sess.sequence_next += 1
    assert len(sess.sequence_layout) == before - 1


def test_challenge_blocked_when_too_much_paint(p: TeamTerritoryParams) -> None:
    from app.games.team_territory.room_engine import start_challenge_if_allowed

    room = _room_with_players(["a", "b"], ready=[True, True])
    room.start_match(utcnow())
    room.players["a"].paint = 6
    sess, err = start_challenge_if_allowed(room, "a", utcnow(), ["word"])
    assert sess is None
    assert err == "too_much_paint"

    room.players["a"].paint = 5
    sess2, err2 = start_challenge_if_allowed(room, "a", utcnow(), ["word"])
    assert err2 is None
    assert sess2 is not None


def test_spelling_words_by_locale() -> None:
    from app.games.team_territory.challenge import load_spelling_words, normalize_spelling_locale
    from app.games.team_territory.constants import tt_params

    p = tt_params()
    en = load_spelling_words(p, "en")
    ru = load_spelling_words(p, "ru")
    assert len(en) >= 100
    assert len(ru) >= 100
    assert all(w.isascii() for w in en[:20])
    assert any("\u0400" <= c <= "\u04ff" for w in ru[:20] for c in w)
    assert normalize_spelling_locale("ru-RU") == "ru"
    assert normalize_spelling_locale("xx") == "en"


def test_sequence_round_uses_longer_timer(p: TeamTerritoryParams) -> None:
    from app.games.team_territory.challenge import ChallengeSession

    now = utcnow()
    sess = ChallengeSession(
        challenge_id="t",
        username="u",
        mode=3,
        params=p,
        started_at_utc=now,
    )
    sess.start_round(now)
    assert sess._round_seconds() == 8
    assert sess.round_deadline_at is not None
    assert (sess.round_deadline_at - now).total_seconds() == 8


def test_math_round_uses_7_second_timer(p: TeamTerritoryParams) -> None:
    from app.games.team_territory.challenge import ChallengeSession

    now = utcnow()
    sess = ChallengeSession(
        challenge_id="t",
        username="u",
        mode=1,
        params=p,
        started_at_utc=now,
    )
    sess.start_round(now)
    assert sess._round_seconds() == 7
    assert (sess.round_deadline_at - now).total_seconds() == 7


def test_detect_horizontal_triple() -> None:
    from app.games.team_territory.combos import register_new_combos

    g = 5
    cells = [-1] * (g * g)
    cells[0] = cells[1] = 0
    completed: set[tuple[int, int, int]] = set()
    counts: dict[int, int] = {}
    combo_cells: set[int] = set()
    combo_centers: set[int] = set()
    cells[2] = 0
    n = register_new_combos(cells, g, [2], completed, counts, combo_cells, combo_centers)
    assert n == 1
    assert counts[0] == 1
    assert combo_cells == {0, 1, 2}
    assert combo_centers == {1}


def test_extend_line_after_combo_does_not_count_overlap() -> None:
    from app.games.team_territory.combos import register_new_combos

    g = 6
    cells = [-1] * (g * g)
    for i in range(3):
        cells[i] = 1
    completed: set[tuple[int, int, int]] = set()
    counts: dict[int, int] = {1: 1}
    combo_cells: set[int] = {0, 1, 2}
    completed.add((0, 1, 2))
    cells[3] = 1
    n = register_new_combos(cells, g, [3], completed, counts, combo_cells)
    assert n == 0
    assert counts[1] == 1
    assert combo_cells == {0, 1, 2}


def test_separate_combos_same_tick() -> None:
    from app.games.team_territory.combos import register_new_combos

    g = 10
    cells = [-1] * (g * g)
    cells[0] = cells[1] = cells[2] = 0
    cells[10] = cells[11] = cells[12] = 0
    completed: set[tuple[int, int, int]] = set()
    counts: dict[int, int] = {}
    combo_cells: set[int] = set()
    combo_centers: set[int] = set()
    n = register_new_combos(cells, g, [2, 12], completed, counts, combo_cells, combo_centers)
    assert n == 2
    assert counts[0] == 2
    assert combo_cells == {0, 1, 2, 10, 11, 12}
    assert combo_centers == {1, 11}


def test_combo_cells_reject_claim(p: TeamTerritoryParams) -> None:
    room = _room_with_players(["a", "b"], ready=[True, True])
    room.start_match(utcnow())
    room.combo_cells = {0}
    room.cells[0] = 0
    pl = room.players["a"]
    pl.claim_cell = 0
    pl.paint = 5
    room.next_tick_at = utcnow() - timedelta(seconds=1)
    room.process_tick(utcnow())
    assert room.cells[0] == 0
    assert pl.paint == 5


def test_finish_winner_uses_combo_bonus(p: TeamTerritoryParams) -> None:
    room = TerritoryRoom(room_id="t", num_teams=2)
    room.phase = "playing"
    room.g = 3
    room.cells = [0, 0, 0, 1, 1, -1, -1, -1, -1]
    room.combo_counts = {0: 1, 1: 0}
    room.combo_cells = {0, 1, 2}
    room.match_team_sizes = {0: 2, 1: 1}
    room._finish_match(utcnow(), "time_up")
    assert room.scores[0] == 3
    assert room.scores[1] == 2
    assert room.combo_bonus[0] == 1
    assert room.balance_bonus[1] == 2  # 2 cells * (2/1 - 1)
    assert room.final_scores[0] == 4
    assert room.final_scores[1] == 4
    assert set(room.winning_team_ids) == {0, 1}


def test_lobby_teams_imbalanced_blocks_start() -> None:
    room = TerritoryRoom(room_id="t", num_teams=2)
    room.players["a"] = PlayerSlot(username="a", team_id=0, role="player", ready=True)
    room.players["b"] = PlayerSlot(username="b", team_id=0, role="player", ready=True)
    room.players["c"] = PlayerSlot(username="c", team_id=0, role="player", ready=True)
    room.players["d"] = PlayerSlot(username="d", team_id=1, role="player", ready=True)
    assert room.lobby_teams_imbalanced() is True
    assert room.can_start_match(utcnow()) is False


def test_balance_bonus_smaller_team() -> None:
    room = TerritoryRoom(room_id="t", num_teams=2)
    room.phase = "playing"
    room.g = 2
    room.cells = [0, 0, 1, -1]
    room.match_team_sizes = {0: 3, 1: 1}
    room._finish_match(utcnow(), "time_up")
    assert room.balance_bonus[1] == 2  # 1 cell * (3/1 - 1)
    assert room.balance_bonus[0] == 0


def test_snapshot_includes_teams() -> None:
    room = TerritoryRoom(room_id="t", num_teams=4)
    room.players["alice"] = PlayerSlot(username="alice", team_id=0, role="player")
    snap = room.snapshot("alice", utcnow(), None)
    assert len(snap["teams"]) == 4
    assert snap["teams"][3]["key"] == "yellow"
    assert snap["teams"][0]["hex"]
    assert "alice" in snap["players"]
    assert snap["me"]["team_id"] == 0


def test_match_reward_win_loss_tie_stale(p: TeamTerritoryParams) -> None:
    from app.games.team_territory.rewards import player_match_reward_diamonds, player_match_reward_kind

    room = TerritoryRoom(room_id="t", num_teams=2)
    room.phase = "finished"
    room.finish_reason = "time_up"
    room.winning_team_ids = [0]
    room.match_team_sizes = {0: 2, 1: 1}

    winner = PlayerSlot(username="w", team_id=0, role="player", ticks_in_match=5)
    loser = PlayerSlot(username="l", team_id=1, role="player", ticks_in_match=5)
    idle = PlayerSlot(username="i", team_id=0, role="player", ticks_in_match=1)
    room.players["w"] = winner
    room.players["l"] = loser
    room.players["i"] = idle

    assert player_match_reward_kind(room, winner, p) == "win"
    assert player_match_reward_diamonds(room, winner, p) == 50
    assert player_match_reward_kind(room, loser, p) == "loss"
    assert player_match_reward_diamonds(room, loser, p) == 10
    assert player_match_reward_kind(room, idle, p) == "none"
    assert player_match_reward_diamonds(room, idle, p) == 0

    room.winning_team_ids = [0, 1]
    assert player_match_reward_kind(room, winner, p) == "tie"
    assert player_match_reward_diamonds(room, winner, p) == 10

    room.finish_reason = "stale_idle"
    room.winning_team_ids = []
    assert player_match_reward_kind(room, winner, p) == "stale_idle"
    assert player_match_reward_diamonds(room, winner, p) == 0

    room.finish_reason = "opponent_left"
    assert player_match_reward_kind(room, winner, p) == "stale_idle"
    assert player_match_reward_diamonds(room, winner, p) == 0

    room.finish_reason = "one_sided_idle"
    assert player_match_reward_kind(room, winner, p) == "stale_idle"
    assert player_match_reward_diamonds(room, winner, p) == 0

    room.finish_reason = "time_up"
    room.winning_team_ids = [0]
    room.players.clear()
    room.players["solo"] = PlayerSlot(username="solo", team_id=0, role="player", ticks_in_match=10)
    room.match_team_sizes = {0: 1}
    solo = room.players["solo"]
    assert player_match_reward_kind(room, solo, p) == "none"
    assert player_match_reward_diamonds(room, solo, p) == 0


def test_winner_reward_when_opponent_has_no_ticks(p: TeamTerritoryParams) -> None:
    from app.games.team_territory.rewards import player_match_reward_diamonds, player_match_reward_kind

    room = TerritoryRoom(room_id="t", num_teams=2)
    room.phase = "finished"
    room.finish_reason = "time_up"
    room.winning_team_ids = [0]
    room.match_team_sizes = {0: 1, 1: 1}
    room.players["w"] = PlayerSlot(username="w", team_id=0, role="player", ticks_in_match=5)
    room.players["l"] = PlayerSlot(username="l", team_id=1, role="player", ticks_in_match=0)
    assert player_match_reward_kind(room, room.players["w"], p) == "win"
    assert player_match_reward_diamonds(room, room.players["w"], p) == 50
    assert player_match_reward_kind(room, room.players["l"], p) == "none"
    assert player_match_reward_diamonds(room, room.players["l"], p) == 0


def test_rewards_allowed_with_debug_solo_flag(p: TeamTerritoryParams, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import config
    from app.games.team_territory.rewards import match_rewards_allowed, match_rewards_block_reason

    monkeypatch.setattr(config.settings, "team_territory_debug_solo_lobby", True)
    monkeypatch.setattr(config.settings, "gamehub_env", "development")
    room = _room_with_players(["a", "b"], ready=[True, True])
    room.players["a"].team_id = 0
    room.players["b"].team_id = 1
    room.start_match(utcnow())
    room.phase = "finished"
    room.finish_reason = "time_up"
    assert match_rewards_allowed(room, p) is True
    assert match_rewards_block_reason(room, p) is None


def test_opponent_left_finishes_after_grace(p: TeamTerritoryParams) -> None:
    room = _room_with_players(["a", "b"], ready=[True, True])
    room.start_match(utcnow())
    room.players["b"].connected = False
    now = utcnow()
    room.insufficient_teams_online_since = now - timedelta(seconds=p.opponent_left_grace_sec + 1)
    assert room.maybe_finish_opponent_left(now) is True
    assert room.phase == "finished"
    assert room.finish_reason == "opponent_left"
    assert room.winning_team_ids == []


def test_opponent_left_grace_not_expired(p: TeamTerritoryParams) -> None:
    room = _room_with_players(["a", "b"], ready=[True, True])
    room.start_match(utcnow())
    room.players["b"].connected = False
    now = utcnow()
    room.maybe_finish_opponent_left(now)
    assert room.phase == "playing"
    assert room.insufficient_teams_online_since is not None


def test_one_sided_idle_finishes_when_only_one_team_active(p: TeamTerritoryParams, monkeypatch) -> None:
    from app.games.team_territory import room_engine

    monkeypatch.setattr(room_engine, "tt_params", lambda: p)
    room = _room_with_players(["a", "b"], ready=[True, True])
    room.players["a"].team_id = 0
    room.players["b"].team_id = 1
    now = utcnow()
    room.start_match(now)
    room.match_started_at = now - timedelta(seconds=p.one_sided_idle_sec + 1)
    room.touch_activity(now, team_id=0)
    assert room.maybe_finish_one_sided_idle(now) is True
    assert room.phase == "finished"
    assert room.finish_reason == "one_sided_idle"
    assert room.winning_team_ids == []


def test_one_sided_idle_not_when_both_teams_active(p: TeamTerritoryParams, monkeypatch) -> None:
    from app.games.team_territory import room_engine

    monkeypatch.setattr(room_engine, "tt_params", lambda: p)
    room = _room_with_players(["a", "b"], ready=[True, True])
    room.players["a"].team_id = 0
    room.players["b"].team_id = 1
    now = utcnow()
    room.start_match(now)
    room.touch_activity(now, team_id=0)
    room.touch_activity(now, team_id=1)
    assert room.maybe_finish_one_sided_idle(now) is False
    assert room.phase == "playing"


def test_reconnect_clears_opponent_left_timer(p: TeamTerritoryParams) -> None:
    room = _room_with_players(["a", "b"], ready=[True, True])
    room.start_match(utcnow())
    room.players["b"].connected = False
    room._track_insufficient_teams_online(utcnow())
    assert room.insufficient_teams_online_since is not None
    room.players["b"].connected = True
    room._track_insufficient_teams_online(utcnow())
    assert room.insufficient_teams_online_since is None
