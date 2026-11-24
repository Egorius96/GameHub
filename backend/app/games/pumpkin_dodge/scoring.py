from __future__ import annotations

from collections.abc import Callable

DIAMOND_EVERY_SECONDS = 20
MAX_SURVIVAL_SECONDS = 6 * 60 * 60


def normalize_survival_seconds(seconds: int) -> int:
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        value = 0
    return max(0, min(value, MAX_SURVIVAL_SECONDS))


def diamonds_for_survival(seconds: int) -> int:
    """1 алмаз за каждые полные 20 секунд прожитого времени."""
    return normalize_survival_seconds(seconds) // DIAMOND_EVERY_SECONDS


def credited_seconds(reported: int, elapsed: int) -> int:
    """Не больше заявленного клиентом и не больше времени партии.

    Две секунды запаса закрывают задержку сети между /start и первым кадром.
    """
    try:
        elapsed_value = int(elapsed)
    except (TypeError, ValueError):
        elapsed_value = 0
    allowed = max(0, elapsed_value) + 2
    return min(normalize_survival_seconds(reported), allowed)


def apply_survival_result(progress: dict, diamonds: int, seconds: int) -> dict:
    """Обновляет рекорд и playtime. Возвращает итог партии, не мутируя баланс снаружи."""
    played = normalize_survival_seconds(seconds)
    awarded = played // DIAMOND_EVERY_SECONDS
    best = max(int(progress.get("high_score_seconds") or 0), played)
    playtime = int(progress.get("playtime") or 0) + played
    progress["high_score_seconds"] = best
    progress["playtime"] = playtime
    return {
        "seconds": played,
        "high_score_seconds": best,
        "playtime": playtime,
        "diamonds_awarded": awarded,
        "diamonds": int(diamonds) + awarded,
    }


def high_score_of(other_data: dict | None, game_key: str) -> int:
    games = (other_data or {}).get("games") or {}
    game = games.get(game_key) or {}
    try:
        return int(game.get("high_score_seconds") or 0)
    except (TypeError, ValueError):
        return 0


def pick_leaderboard(
    users: list[dict],
    score_of: Callable[[dict], int],
    username: str,
    limit: int,
    fallback: dict | None,
) -> list[dict]:
    """Топ как в Pro Racing: limit записей, текущий игрок остаётся в списке, если он ниже среза."""
    ranked = sorted(users, key=score_of, reverse=True)
    top = ranked[:limit]
    if any(user.get("username") == username for user in top):
        return top
    current = next((user for user in ranked if user.get("username") == username), None)
    if current is None:
        current = fallback
    if current is None:
        return top
    if limit > 0 and len(top) >= limit:
        return top[:-1] + [current]
    return top + [current]
