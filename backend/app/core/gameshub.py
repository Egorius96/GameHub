from __future__ import annotations

from app.core.config import settings
from app.services.catalog import get_catalog_games


def _ensure_games_dict(other_data: dict) -> dict:
    games = other_data.get("games")
    if not isinstance(games, dict):
        games = {}
        other_data["games"] = games
    return games


def _ensure_game_progress_defaults(game_key: str, progress: dict) -> dict:
    if game_key == settings.pro_racing_game_key:
        progress.setdefault("car_level", 1)
        progress.setdefault("two_players_gamemode", False)
        progress.setdefault("matches_count", 0)
        progress.setdefault("high_score_seconds", 0)
        progress.setdefault(
            "superpowers",
            {
                "drugs": False,
                "immue": False,
                "time_stop": False,
                "minigun": False,
                "rockspeed": False,
                "hearty_rock": False,
            },
        )
        progress.setdefault("playtime", 0)
    elif game_key == settings.rps_game_key:
        progress.setdefault("playtime", 0)
    elif game_key == settings.tamagochi_game_key:
        progress.setdefault("playtime", 0)
        progress.setdefault("pet", None)
        progress.setdefault("pet_state", None)
        progress.setdefault("last_update_at", None)
        progress.setdefault("neglect", {})
        progress.setdefault("coins", 0)
        progress.setdefault(
            "inventory",
            {
                "food_by_type": {"cat": 0, "dog": 0, "pokemon": 0, "capybara": 0, "alien": 0},
                "toy": 0,
            },
        )
        progress.setdefault("shop", {})
        progress.setdefault("toy_until", None)
    elif game_key == settings.team_territory_game_key:
        progress.setdefault("playtime", 0)
        progress.setdefault("match_rewards", {})
    elif game_key == settings.minecraft_2d_online_game_key:
        progress.setdefault("playtime", 0)
        progress.setdefault("diamond_dust", 0)
        progress.setdefault("dust_exchange_rate", 14)
        progress.setdefault("dust_rate_history", [])
        progress.setdefault("exchange_idempotency", {})
        progress.setdefault("deliver_idempotency", {})
    else:
        progress.setdefault("playtime", 0)
    return progress


def ensure_pro_racing_schema(other_data: dict) -> dict:
    """
    Ensures schema:
      other_data.diamonds -> shared currency
      other_data[settings.pro_racing_game_key] -> per-game dict

    Backward compatibility:
      If old per-game fields are at top-level, they are moved into the game dict.
    """
    other_data = other_data or {}
    diamonds = int(other_data.get("diamonds", 0))
    games = _ensure_games_dict(other_data)
    game_key = settings.pro_racing_game_key
    game = games.get(game_key)
    if not isinstance(game, dict):
        game = {}
        games[game_key] = game

    # migrate old schema fields into game dict (if present on top-level legacy)
    migrate_keys = [
        "car_level",
        "two_players_gamemode",
        "matches_count",
        "high_score_seconds",
        "superpowers",
        "last_login_at",
    ]
    for k in migrate_keys:
        if k in other_data and k not in game:
            game[k] = other_data.get(k)

    # handle legacy playtime formats:
    # - int seconds
    # - dict (e.g., {"pro_racing_game": seconds})
    if "playtime" in other_data and "playtime" not in game:
        legacy = other_data.get("playtime")
        if isinstance(legacy, (int, float, str)):
            try:
                game["playtime"] = int(legacy)
            except ValueError:
                game["playtime"] = 0
        elif isinstance(legacy, dict):
            # best-effort: sum numeric values
            total = 0
            for v in legacy.values():
                try:
                    total += int(v)
                except Exception:
                    continue
            game["playtime"] = total

    _ensure_game_progress_defaults(game_key, game)
    game_playtime = game.get("playtime", 0)
    if isinstance(game_playtime, dict):
        # sanitize if somehow persisted as dict
        total = 0
        for v in game_playtime.values():
            try:
                total += int(v)
            except Exception:
                continue
        game["playtime"] = total
    else:
        try:
            game["playtime"] = int(game_playtime)
        except Exception:
            game["playtime"] = 0

    other_data["diamonds"] = diamonds
    games[game_key] = game

    # keep top-level clean (optional, but avoids mixing)
    for k in migrate_keys:
        other_data.pop(k, None)
    other_data.pop("playtime", None)

    return other_data


def ensure_gameshub_schema(other_data: dict) -> dict:
    other_data = ensure_pro_racing_schema(other_data)
    diamonds = int(other_data.get("diamonds", 0))
    other_data["diamonds"] = diamonds
    av = other_data.get("avatar_url")
    if av is None or (isinstance(av, str) and not str(av).strip()):
        other_data["avatar_url"] = settings.default_avatar_url

    games = _ensure_games_dict(other_data)
    catalog_games = get_catalog_games()
    for game_key in catalog_games.keys():
        progress = games.get(game_key)
        if not isinstance(progress, dict):
            progress = {}
        games[game_key] = _ensure_game_progress_defaults(game_key, progress)

    return other_data


def get_pro_racing_game(other_data: dict) -> dict:
    other_data = ensure_pro_racing_schema(other_data)
    games = _ensure_games_dict(other_data)
    return games[settings.pro_racing_game_key]

