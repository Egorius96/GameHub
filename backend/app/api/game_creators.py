from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile

from app.core.config import settings
from app.core.session import sessions
from app.integrations.users_api import users_api
from app.services.catalog import (
    author_env_password_for_game,
    default_catalog_other_data,
    merge_creator_defaults_into_catalog_games,
)
from app.services.game_creator_upload import (
    MAX_CREATOR_UPLOAD_BYTES,
    remove_previous_creator_files,
    save_game_creator_photo,
)

router = APIRouter(prefix="/api/game-creators", tags=["game_creators"])

_CREATOR_DIR = Path(__file__).resolve().parent.parent / "static" / "game_creators"

_KNOWN_KEYS = frozenset(
    {
        settings.pro_racing_game_key,
        settings.rps_game_key,
        settings.tamagochi_game_key,
        settings.team_territory_game_key,
        settings.minecraft_2d_online_game_key,
    }
)


def _not_configured_exc() -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "code": "author_password_not_configured",
            "message": "В переменных окружения не задан пароль автора для этой игры.",
        },
    )


def _wrong_password_exc() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"code": "wrong_author_password", "message": "Пароль неверный."},
    )


def _load_catalog_user() -> dict:
    user = users_api.auth(settings.catalog_username, settings.catalog_password)
    if user.get("error") == "connection":
        raise HTTPException(status_code=503, detail="catalog_unavailable")
    if not user.get("username"):
        raise HTTPException(status_code=503, detail="catalog_missing")
    other = user.setdefault("other_data", {})
    games = other.setdefault("games", {})
    if not isinstance(games, dict):
        other["games"] = dict((default_catalog_other_data().get("games") or {}))
    merge_creator_defaults_into_catalog_games(other)
    return user


def _verify_author_password(gk: str, password: str) -> None:
    expected = author_env_password_for_game(gk)
    if not expected:
        raise _not_configured_exc()
    if (password or "").strip() != expected:
        raise _wrong_password_exc()


@router.post("/update")
async def update_creator_block(
    authorization: str = Header(default=""),
    game_key: str = Form(...),
    password: str = Form(""),
    message: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
) -> dict:
    token = authorization.replace("Bearer ", "").strip()
    if not token or token not in sessions:
        raise HTTPException(status_code=401, detail="Unauthorized")

    gk = (game_key or "").strip()
    if gk not in _KNOWN_KEYS:
        raise HTTPException(status_code=400, detail="unknown_game")

    _verify_author_password(gk, password)

    raw_file: bytes | None = None
    if file is not None and file.filename:
        raw_file = await file.read()
        if len(raw_file) > MAX_CREATOR_UPLOAD_BYTES:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "creator_file_too_large",
                    "message": "Фото слишком большое: максимум 5 МБ до сжатия.",
                },
            )

    if message is None and not raw_file:
        raise HTTPException(status_code=400, detail="nothing_to_update")

    user = _load_catalog_user()
    other = user["other_data"]
    games = other.get("games")
    if not isinstance(games, dict):
        raise HTTPException(status_code=503, detail="catalog_corrupt")

    meta = games.get(gk)
    if not isinstance(meta, dict):
        meta = dict((default_catalog_other_data().get("games") or {}).get(gk, {}))
        games[gk] = meta

    if message is not None:
        meta["creator_message"] = (message or "").strip()[:2000]
    if raw_file:
        try:
            url = save_game_creator_photo(game_key=gk, data=raw_file, dest_dir=_CREATOR_DIR)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Укажите корректное изображение (JPEG, PNG, GIF, WebP и др.)",
            )
        meta["creator_avatar_url"] = url

    users_api.save_user(user)
    return {"ok": True, "creator_avatar_url": meta.get("creator_avatar_url"), "creator_message": meta.get("creator_message")}


@router.post("/reset")
async def reset_creator_block(
    authorization: str = Header(default=""),
    game_key: str = Form(...),
    password: str = Form(""),
) -> dict:
    token = authorization.replace("Bearer ", "").strip()
    if not token or token not in sessions:
        raise HTTPException(status_code=401, detail="Unauthorized")

    gk = (game_key or "").strip()
    if gk not in _KNOWN_KEYS:
        raise HTTPException(status_code=400, detail="unknown_game")

    _verify_author_password(gk, password)

    user = _load_catalog_user()
    other = user["other_data"]
    games = other.get("games")
    if not isinstance(games, dict):
        raise HTTPException(status_code=503, detail="catalog_corrupt")

    meta = games.get(gk)
    if not isinstance(meta, dict):
        meta = dict((default_catalog_other_data().get("games") or {}).get(gk, {}))
        games[gk] = meta

    remove_previous_creator_files(_CREATOR_DIR, gk)
    meta["creator_message"] = ""
    meta["creator_avatar_url"] = None

    users_api.save_user(user)
    return {"ok": True, "creator_avatar_url": None, "creator_message": ""}
