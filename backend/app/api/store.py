from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from app.core.session import sessions
from app.core.gameshub import ensure_pro_racing_schema, get_pro_racing_game
from app.integrations.users_api import users_api
from app.schemas.store import BuySuperpowerRequest, UpgradeCarResponse

router = APIRouter(prefix="/api/store", tags=["store"])

CARS_COSTS = {1: 0, 2: 20, 3: 100}
SUPER_COSTS = {"drugs": 50, "immue": 200, "rockspeed": 300, "hearty_rock": 100}


def _session_from_auth(authorization: str):
    token = authorization.replace("Bearer ", "")
    session = sessions.get(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return session


@router.post("/upgrade-car", response_model=UpgradeCarResponse)
def upgrade_car(authorization: str = Header(default="")) -> UpgradeCarResponse:
    session = _session_from_auth(authorization)
    other_data = ensure_pro_racing_schema(session.user["other_data"])
    game = get_pro_racing_game(other_data)
    level = int(game.get("car_level", 1))
    if level >= 3:
        raise HTTPException(status_code=400, detail="Max car level")

    cost = CARS_COSTS[level + 1]
    diamonds = int(other_data.get("diamonds", 0))
    if diamonds < cost:
        raise HTTPException(status_code=400, detail=f"Need {cost - diamonds} diamonds")

    other_data["diamonds"] = diamonds - cost
    game["car_level"] = level + 1
    session.user["other_data"] = other_data
    users_api.save_user(session.user)
    return UpgradeCarResponse(car_level=int(game["car_level"]), diamonds=int(other_data["diamonds"]))


@router.post("/buy-superpower")
def buy_superpower(payload: BuySuperpowerRequest, authorization: str = Header(default="")) -> dict:
    session = _session_from_auth(authorization)
    if payload.superpower not in SUPER_COSTS:
        raise HTTPException(status_code=400, detail="Unknown superpower")

    other_data = ensure_pro_racing_schema(session.user["other_data"])
    game = get_pro_racing_game(other_data)
    superpowers = game.setdefault("superpowers", {})
    if superpowers.get(payload.superpower):
        raise HTTPException(status_code=400, detail="Already purchased")

    cost = SUPER_COSTS[payload.superpower]
    diamonds = int(other_data.get("diamonds", 0))
    if diamonds < cost:
        raise HTTPException(status_code=400, detail=f"Need {cost - diamonds} diamonds")

    other_data["diamonds"] = diamonds - cost
    superpowers[payload.superpower] = True
    session.user["other_data"] = other_data
    users_api.save_user(session.user)
    return {"diamonds": other_data["diamonds"], "superpowers": superpowers}
