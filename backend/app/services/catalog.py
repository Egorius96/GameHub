from __future__ import annotations

from app.core.config import settings
from app.integrations.users_api import users_api


def default_catalog_other_data() -> dict:
    return {
        "games": {
            settings.pro_racing_game_key: {
                "title": "Pro Racing",
                "description": "Аркадные гонки с камнями, алмазами и улучшениями.",
                "game_author": None,
                "creator_avatar_url": None,
                "creator_message": "",
                "status": "released",
            },
            settings.rps_game_key: {
                "title": "Камень ножницы бумага",
                "description": "Классическая игра: робот, онлайн-комнаты и ставки алмазами.",
                "game_author": None,
                "creator_avatar_url": None,
                "creator_message": "",
                "status": "released",
            },
            settings.tamagochi_game_key: {
                "title": "Тамагочи World",
                "description": "Мир питомцев: кормите, играйте, укладывайте спать и наблюдайте за другими.",
                "game_author": None,
                "creator_avatar_url": None,
                "creator_message": "",
                "status": "released",
            },
            settings.team_territory_game_key: {
                "title": "Team Territory",
                "description": "Закрасьте поле G×G быстрее соперников: тики, краска, Challenge и награды алмазами.",
                "game_author": None,
                "creator_avatar_url": None,
                "creator_message": "",
                "status": "coming_soon",
            },
            settings.minecraft_2d_online_game_key: {
                "title": "Minecraft 2D Online",
                "description": "2D-копание, очередь в мир, пыль и обмен с алмазами GameHub.",
                "game_author": None,
                "creator_avatar_url": None,
                "creator_message": "",
                "status": "released",
            },
        }
    }


def author_env_password_for_game(game_key: str) -> str | None:
    """Непустой пароль из .env для игры или None, если защита автора не настроена."""
    s = ""
    if game_key == settings.pro_racing_game_key:
        s = (settings.pro_racing_author or "").strip()
    elif game_key == settings.rps_game_key:
        s = (settings.rps_author or "").strip()
    elif game_key == settings.tamagochi_game_key:
        s = (settings.tamagochi_author or "").strip()
    elif game_key == settings.team_territory_game_key:
        s = (settings.team_territory_author or "").strip()
    elif game_key == settings.minecraft_2d_online_game_key:
        s = (settings.minecraft_2d_author or "").strip()
    return s if s else None


def _merge_creator_keys_into_game_dict(game_key: str, meta: dict) -> bool:
    defaults = (default_catalog_other_data().get("games") or {}).get(game_key)
    if not isinstance(defaults, dict):
        return False
    changed = False
    for k in ("creator_avatar_url", "creator_message"):
        if k not in meta and k in defaults:
            meta[k] = defaults[k]
            changed = True
    return changed


def merge_creator_defaults_into_catalog_games(other: dict) -> bool:
    games = other.get("games")
    if not isinstance(games, dict):
        return False
    changed = False
    for key, meta in list(games.items()):
        if isinstance(meta, dict) and _merge_creator_keys_into_game_dict(key, meta):
            changed = True
    return changed


def _merge_missing_catalog_games(other: dict) -> list[str]:
    """
    Дописывает в other['games'] метаданные игр из дефолта, если ключей не хватает
    (миграция после добавления новых игр в код).
    """
    defaults = default_catalog_other_data().get("games") or {}
    if not isinstance(defaults, dict):
        return []
    games = other.get("games")
    if not isinstance(games, dict):
        return []
    added: list[str] = []
    for key, meta in defaults.items():
        if key not in games:
            games[key] = dict(meta) if isinstance(meta, dict) else meta
            added.append(key)
    return added


def migrate_catalog_missing_games() -> dict:
    """
    Явная миграция: дописать недостающие записи каталога у пользователя gamehub_catalog.
    Безопасно вызывать многократно.
    """
    user = users_api.auth(settings.catalog_username, settings.catalog_password)
    if user.get("error") == "connection":
        return {"ok": False, "added": [], "error": "users_api_connection"}
    if not user.get("username"):
        return {"ok": False, "added": [], "error": "catalog_user_not_found"}

    other = user.setdefault("other_data", {})
    if not isinstance(other.get("games"), dict):
        other.update(default_catalog_other_data())
        users_api.save_user(user)
        added = list((default_catalog_other_data().get("games") or {}).keys())
        return {"ok": True, "added": added, "error": None}

    added = _merge_missing_catalog_games(other)
    if added:
        users_api.save_user(user)
    return {"ok": True, "added": added, "error": None}


def ensure_catalog_exists() -> dict | None:
    """
    Ensures a single system user exists whose other_data.games contains game metadata.
    Returns catalog user dict (as returned by users api) or None if users api unavailable.
    """
    user = users_api.auth(settings.catalog_username, settings.catalog_password)
    if user.get("error") == "connection":
        return None
    if user.get("username"):
        other = user.setdefault("other_data", {})
        if not isinstance(other.get("games"), dict):
            other.update(default_catalog_other_data())
            users_api.save_user(user)
        else:
            added = _merge_missing_catalog_games(other)
            creator_added = merge_creator_defaults_into_catalog_games(other)
            if added or creator_added:
                users_api.save_user(user)
        return user

    # create catalog user
    created = users_api.create_user(settings.catalog_username, settings.catalog_password, default_catalog_other_data())
    if created.get("error") == "connection":
        return None
    return created


def get_catalog_games() -> dict:
    user = ensure_catalog_exists()
    if not user or not user.get("other_data"):
        games = dict(default_catalog_other_data()["games"])
    else:
        other = user.get("other_data") or {}
        games = other.get("games") or {}
        if not isinstance(games, dict):
            games = dict(default_catalog_other_data()["games"])
    defaults = default_catalog_other_data()["games"] or {}
    out: dict = {}
    for key, dmeta in defaults.items():
        base = dict(dmeta) if isinstance(dmeta, dict) else {}
        umeta = games.get(key)
        if isinstance(umeta, dict):
            base.update(umeta)
        if key == settings.rps_game_key:
            desc = str(base.get("description") or "")
            if "в разработке" in desc.lower() or base.get("status") == "coming_soon":
                base["description"] = str(dmeta.get("description") or desc)
                base["status"] = str(dmeta.get("status") or "released")
        _merge_creator_keys_into_game_dict(key, base)
        base["author_password_configured"] = bool(author_env_password_for_game(key))
        out[key] = base
    for key, umeta in games.items():
        if key in out or not isinstance(umeta, dict):
            continue
        base = dict(umeta)
        _merge_creator_keys_into_game_dict(key, base)
        base["author_password_configured"] = bool(author_env_password_for_game(key))
        out[key] = base
    return out

