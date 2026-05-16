from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.session import UserSession, sessions
from app.games.rps.robot_sessions import robot_sessions
from app.games.rps.rooms import rps_room_manager

router = APIRouter(prefix="/api/rps", tags=["rps"])


def _session_from_header(authorization: str = Header(default="")) -> UserSession:
    token = authorization.replace("Bearer ", "")
    sess = sessions.get(token)
    if sess is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return sess


@router.get("/rooms")
def list_rooms(_: UserSession = Depends(_session_from_header)) -> dict:
    return {"rooms": rps_room_manager.public_lobby_snapshot()}


class RobotSessionBody(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)


class RobotPickBody(RobotSessionBody):
    move: str = Field(min_length=3, max_length=16)


class RobotPlayBody(RobotPickBody):
    pass


class RobotClaimBody(RobotSessionBody):
    pass


@router.post("/robot/start")
def robot_start(sess: UserSession = Depends(_session_from_header)) -> dict:
    if sess.username == "admindb":
        raise HTTPException(status_code=400, detail="admin cannot play")
    return robot_sessions.start(sess.username)


@router.get("/robot/state")
def robot_state(session_id: str, sess: UserSession = Depends(_session_from_header)) -> dict:
    out = robot_sessions.state(session_id, sess.username)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out)
    return out


@router.post("/robot/pick")
def robot_pick(body: RobotPickBody, sess: UserSession = Depends(_session_from_header)) -> dict:
    if sess.username == "admindb":
        raise HTTPException(status_code=400, detail="admin cannot play")
    out = robot_sessions.pick(body.session_id, sess.username, body.move)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out)
    return out


@router.post("/robot/resolve")
def robot_resolve(body: RobotSessionBody, sess: UserSession = Depends(_session_from_header)) -> dict:
    if sess.username == "admindb":
        raise HTTPException(status_code=400, detail="admin cannot play")
    out = robot_sessions.resolve(body.session_id, sess.username)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out)
    return out


@router.post("/robot/next_round")
def robot_next_round(body: RobotSessionBody, sess: UserSession = Depends(_session_from_header)) -> dict:
    if sess.username == "admindb":
        raise HTTPException(status_code=400, detail="admin cannot play")
    out = robot_sessions.next_round(body.session_id, sess.username)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out)
    return out


@router.post("/robot/play")
def robot_play(body: RobotPlayBody, sess: UserSession = Depends(_session_from_header)) -> dict:
    if sess.username == "admindb":
        raise HTTPException(status_code=400, detail="admin cannot play")
    out = robot_sessions.play(body.session_id, sess.username, body.move)
    if not out.get("ok"):
        code = str(out.get("error") or "play_error")
        if code == "too_fast_round":
            raise HTTPException(status_code=429, detail=out)
        raise HTTPException(status_code=400, detail=out)
    return out


@router.post("/robot/claim")
def robot_claim(body: RobotClaimBody, sess: UserSession = Depends(_session_from_header)) -> dict:
    if sess.username == "admindb":
        raise HTTPException(status_code=400, detail="admin cannot play")
    out = robot_sessions.claim(body.session_id, sess.username)
    if not out.get("ok"):
        if out.get("error") == "too_fast_total":
            raise HTTPException(status_code=429, detail=out)
        raise HTTPException(status_code=400, detail=out)
    return out
