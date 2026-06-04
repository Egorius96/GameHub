from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core.session import sessions
from app.core.gameshub import ensure_gameshub_schema
from app.core.presence import presence
from app.services.avatar_upload import MAX_AVATAR_UPLOAD_BYTES, save_avatar_file
from app.services.catalog import get_catalog_games
from app.integrations.users_api import users_api
from app.db.models import GameHubUser
from app.db.session import _session_factory

router = APIRouter(prefix="/api/profile", tags=["profile"])

_AVATAR_DIR = Path(__file__).resolve().parent.parent / "static" / "avatars"


class HeartbeatRequest(BaseModel):
    game: str = Field(min_length=1, max_length=64)
    seconds: int = Field(ge=1, le=60)


class PatchProfileRequest(BaseModel):
    ui_lang: str | None = Field(default=None, max_length=8)


@router.patch("")
def patch_profile(payload: PatchProfileRequest, authorization: str = Header(default="")) -> dict:
    token = authorization.replace("Bearer ", "")
    session = sessions.get(token)
    if session is None:
        raise HTTPException(status_code=401, detail={"code": "unauthorized"})
    other = ensure_gameshub_schema(session.user.get("other_data") or {})
    if payload.ui_lang is not None:
        lang = payload.ui_lang.strip().lower()
        if lang not in ("en", "ru", "it", "es", "de"):
            raise HTTPException(status_code=400, detail={"code": "invalid_ui_lang"})
        other["ui_lang"] = lang
    session.user["other_data"] = other
    users_api.save_user(session.user)
    return {"ok": True, "other_data": other}


@router.get("")
def get_profile(authorization: str = Header(default="")) -> dict:
    token = authorization.replace("Bearer ", "")
    session = sessions.get(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    presence.touch(session.username, None)
    other = ensure_gameshub_schema(session.user["other_data"])
    session.user["other_data"] = other
    if session.username != "admindb":
        db = _session_factory()()
        try:
            gh = db.query(GameHubUser).filter(GameHubUser.username == session.username).first()
            if gh is not None:
                wc = int(getattr(gh, "warning_count", 0) or 0)
                msg = (getattr(gh, "mod_warning_text", None) or "").strip()
                other["mod_warning"] = {
                    "text": msg,
                    "level": wc,
                    "until_ban": max(0, 3 - wc),
                }
                session.user["other_data"] = other
        finally:
            db.close()
    return {
        "username": session.user["username"],
        "other_data": other,
    }


@router.post("/avatar")
async def upload_avatar(
    authorization: str = Header(default=""),
    file: UploadFile = File(...),
) -> dict:
    token = authorization.replace("Bearer ", "")
    session = sessions.get(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    presence.touch(session.username, None)
    raw = await file.read()
    if len(raw) > MAX_AVATAR_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Файл слишком большой: максимум 5 МБ до сжатия.")
    try:
        url = save_avatar_file(username=session.username, data=raw, dest_dir=_AVATAR_DIR)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Укажите корректное изображение (JPEG, PNG, GIF, WebP и др.)",
        )
    other = ensure_gameshub_schema(session.user.get("other_data") or {})
    other["avatar_url"] = url
    session.user["other_data"] = other
    users_api.save_user(session.user)
    return {"ok": True, "avatar_url": url}


@router.get("/games_catalog")
def games_catalog(authorization: str = Header(default="")) -> dict:
    token = authorization.replace("Bearer ", "")
    session = sessions.get(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    presence.touch(session.username, None)
    return {"games": get_catalog_games()}


@router.post("/heartbeat")
def heartbeat(payload: HeartbeatRequest, authorization: str = Header(default="")) -> dict:
    token = authorization.replace("Bearer ", "")
    session = sessions.get(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    presence.touch(session.username, payload.game)

    other_data = ensure_gameshub_schema(session.user.setdefault("other_data", {}) or {})
    games = other_data.setdefault("games", {})
    if not isinstance(games, dict):
        games = {}
        other_data["games"] = games
    game = games.get(payload.game)
    if not isinstance(game, dict):
        game = {}
        games[payload.game] = game
    try:
        game["playtime"] = int(game.get("playtime", 0)) + int(payload.seconds)
    except Exception:
        game["playtime"] = int(payload.seconds)
    session.user["other_data"] = other_data
    users_api.save_user(session.user)
    return {"ok": True, "playtime": game.get("playtime", 0)}
