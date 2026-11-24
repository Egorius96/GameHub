import pytest

from app.games.pumpkin_dodge.scoring import (
    MAX_SURVIVAL_SECONDS,
    apply_survival_result,
    credited_seconds,
    diamonds_for_survival,
    pick_leaderboard,
)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, 0),
        (19, 0),
        (20, 1),
        (45, 2),
        (60, 3),
        (-5, 0),
        (MAX_SURVIVAL_SECONDS + 100, MAX_SURVIVAL_SECONDS // 20),
    ],
)
def test_diamonds_for_survival(seconds: int, expected: int) -> None:
    assert diamonds_for_survival(seconds) == expected


@pytest.mark.parametrize(
    ("reported", "elapsed", "expected"),
    [
        (100, 5, 7),
        (5, 100, 5),
        (20, 19, 20),
        (0, 40, 0),
        (-10, 40, 0),
        (MAX_SURVIVAL_SECONDS + 50, MAX_SURVIVAL_SECONDS + 50, MAX_SURVIVAL_SECONDS),
    ],
)
def test_credited_seconds_caps_client_claim(reported: int, elapsed: int, expected: int) -> None:
    assert credited_seconds(reported, elapsed) == expected


def test_apply_survival_keeps_best_and_adds_playtime() -> None:
    progress = {"high_score_seconds": 30, "playtime": 10}
    result = apply_survival_result(progress, diamonds=5, seconds=25)
    assert progress["high_score_seconds"] == 30
    assert progress["playtime"] == 35
    assert result["diamonds_awarded"] == 1
    assert result["diamonds"] == 6


def test_apply_survival_raises_high_score() -> None:
    progress = {"high_score_seconds": 10, "playtime": 0}
    apply_survival_result(progress, 0, 40)
    assert progress["high_score_seconds"] == 40
    assert progress["playtime"] == 40


def test_pick_leaderboard_appends_current_player_outside_top() -> None:
    users = [{"username": f"u{i}", "score": 100 - i} for i in range(12)]
    users.append({"username": "me", "score": 0})
    top = pick_leaderboard(users, lambda user: int(user["score"]), "me", 10, None)
    assert len(top) == 10
    assert top[0]["username"] == "u0"
    assert top[-1]["username"] == "me"


def test_pick_leaderboard_does_not_duplicate_current_player() -> None:
    users = [{"username": "me", "score": 50}, {"username": "a", "score": 10}]
    top = pick_leaderboard(users, lambda user: int(user["score"]), "me", 10, None)
    assert [user["username"] for user in top] == ["me", "a"]
