from __future__ import annotations

import zlib
from pathlib import Path

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.core.session import UserSession, sessions
from app.core.gameshub import ensure_gameshub_schema
from app.core.presence import presence
from app.core.client_ip import client_ip
from app.games.tamagochi_world.world import tamagochi_world
from app.integrations.users_api import attempt_insert_gamehub_user, users_api
from app.db.models import GameHubUser, GameHubRegistrationLog
from app.db.session import _session_factory, get_db
from app.schemas.auth import AuthRequest, AuthResponse, DeleteAccountRequest
from app.services.avatar_upload import remove_previous_avatar_files

router = APIRouter(prefix="/api/auth", tags=["auth"])

_AVATAR_DIR = Path(__file__).resolve().parent.parent / "static" / "avatars"

_REGISTRATION_LIMIT_PER_DAY = 2


def _registration_advisory_key(ip: str, day_iso: str) -> int:
    h = zlib.crc32(f"{ip}\0{day_iso}".encode("utf-8")) & 0x7FFFFFFF
    return h if h != 0 else 1


@router.post("/sign-in", response_model=AuthResponse)
def sign_in(payload: AuthRequest) -> AuthResponse:
    if payload.username == "admindb":
        import os

        expected = os.getenv("ADMINDB_PASSWORD", "")
        if not expected or payload.password != expected:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        token = create_access_token("admindb", role="admin")
        user = {"username": "admindb", "password": payload.password, "other_data": {"role": "admin"}}
        sessions[token] = UserSession(username="admindb", password=payload.password, user=user)
        presence.touch("admindb", None)
        return AuthResponse(access_token=token, username="admindb", other_data=user["other_data"])

    user = users_api.auth(payload.username, payload.password)
    if user.get("error"):
        if user.get("error") == "temp_ban":
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "temp_ban",
                    "banned_until": user.get("banned_until"),
                    "seconds_remaining": int(user.get("seconds_remaining") or 0),
                },
            )
        if user.get("error") == "blocked":
            hist = user.get("warnings_history")
            if not isinstance(hist, list):
                hist = []
            raise HTTPException(
                status_code=403,
                detail={"code": "blocked", "warnings_history": hist},
            )
        raise HTTPException(status_code=503, detail="Users API unavailable")
    if not user.get("username"):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    other = user.setdefault("other_data", {})
    other = ensure_gameshub_schema(other)
    games = other.setdefault("games", {})
    if not isinstance(games, dict):
        games = {}
        other["games"] = games
    pro = games.setdefault("misha_pro_racing_game", {})
    if not isinstance(pro, dict):
        pro = {}
        games["misha_pro_racing_game"] = pro
    pro["last_login_at"] = datetime.now(timezone.utc).isoformat()
    user["other_data"] = other
    users_api.save_user(user)

    token = create_access_token(user["username"])
    sessions[token] = UserSession(username=user["username"], password=user["password"], user=user)
    presence.touch(user["username"], None)

    # warnings + login counters
    db = _session_factory()()
    try:
        gh = db.query(GameHubUser).filter(GameHubUser.username == user["username"]).first()
        if gh is not None:
            gh.login_count = int(getattr(gh, "login_count", 0) or 0) + 1
            gh.last_active_at = datetime.now(timezone.utc)
            db.commit()
            wc = int(getattr(gh, "warning_count", 0) or 0)
            msg = (getattr(gh, "mod_warning_text", None) or "").strip()
            other["mod_warning"] = {
                "text": msg,
                "level": wc,
                "until_ban": max(0, 3 - wc),
            }
            other.pop("warnings_active", None)
            other.pop("warnings_total", None)
    finally:
        db.close()

    return AuthResponse(access_token=token, username=user["username"], other_data=other)


@router.post("/register", response_model=AuthResponse)
def register(payload: AuthRequest, request: Request, db: Session = Depends(get_db)) -> AuthResponse:
    ip = (client_ip(request) or "").strip() or "unknown"
    day = datetime.now(timezone.utc).date()
    lock_key = _registration_advisory_key(ip, day.isoformat())

    try:
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock_key})
        n = (
            db.query(func.count(GameHubRegistrationLog.id))
            .filter(GameHubRegistrationLog.ip == ip, GameHubRegistrationLog.day == day)
            .scalar()
            or 0
        )
        if int(n) >= _REGISTRATION_LIMIT_PER_DAY:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "registration_daily_limit",
                    "message": "Для вас сегодня лимит новых регистраций исчерпан: не более 2 новых аккаунтов за сутки. Создать ещё один сейчас нельзя — попробуйте завтра.",
                },
            )

        uname = payload.username.strip()
        ok, u = attempt_insert_gamehub_user(db, uname, payload.password)
        if not ok or u is None:
            db.rollback()
            return sign_in(payload)

        db.add(GameHubRegistrationLog(ip=ip, day=day, user_id=u.id))
        db.commit()
        db.refresh(u)
    except HTTPException:
        db.rollback()
        raise

    user = {
        "username": u.username,
        "password": u.password,
        "project": u.project,
        "other_data": u.other_data or {},
    }
    other = ensure_gameshub_schema(user.get("other_data") or {})
    user["other_data"] = other
    users_api.save_user(user)
    token = create_access_token(user["username"])
    sessions[token] = UserSession(username=user["username"], password=user["password"], user=user)
    presence.touch(user["username"], None)
    return AuthResponse(access_token=token, username=user["username"], other_data=other)


@router.post("/delete-account")
def delete_account(payload: DeleteAccountRequest, authorization: str = Header(default="")) -> dict:
    token = authorization.replace("Bearer ", "")
    session = sessions.get(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    status, body = users_api.delete_user(session.username, payload.password)
    if status == 0:
        raise HTTPException(status_code=503, detail="Users API unavailable")
    if status != 200:
        msg = body.get("detail", "Failed to delete user")
        if status >= 500:
            raise HTTPException(status_code=502, detail=str(msg))
        raise HTTPException(status_code=400, detail=str(msg))

    uname = session.username
    remove_previous_avatar_files(_AVATAR_DIR, uname)
    tamagochi_world.remove_user_everywhere(uname)
    presence.forget(uname)

    for t in [t for t, s in list(sessions.items()) if s.username == uname]:
        sessions.pop(t, None)

    return {"ok": True, "message": body.get("message", "User deleted successfully")}
