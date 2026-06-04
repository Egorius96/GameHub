from __future__ import annotations

from datetime import datetime, timezone
from datetime import timedelta
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.gameshub import ensure_gameshub_schema
from app.core.session import sessions
from app.integrations.users_api import users_api
from app.games.tamagochi_world.actions import ActionType, apply_action
from app.games.tamagochi_world.world import tamagochi_world
from app.games.tamagochi_world.shop import get_shop_prices, item_effects_doc
from app.core.api_errors import api_error
from app.games.tamagochi_world.pet_history import (
    archive_pet,
    ensure_death_archived,
    estimate_best_diamond_interval_minutes,
    pet_age_days,
    pet_needs_attention,
)
from app.games.tamagochi_world.pet_state import (
    PetState,
    PetType,
    is_critical,
    make_new_pet,
    maybe_add_neglect_strike,
    merge_shop_toy_buffs_from_progress,
    register_useful_action,
    register_visit,
    sync_pet_state,
)


router = APIRouter(prefix="/api/tamagochi", tags=["tamagochi"])

_PET_TYPES = ("cat", "dog", "pokemon", "capybara", "alien")

# Лечение за монеты (магазин)
HEAL_COINS_COST = 30
HEAL_HP_POINTS = 10

PLAY_ACTION_COINS_COST = 25
SLEEP_ACTION_COINS_COST = 10
RECREATE_PET_COINS_COST = 50


def _migrate_inventory(progress: dict) -> dict:
    inv = progress.get("inventory")
    if not isinstance(inv, dict):
        inv = {}
    ft = inv.get("food_by_type")
    if not isinstance(ft, dict):
        ft = {}
    for t in _PET_TYPES:
        ft.setdefault(t, 0)
    legacy = int(inv.get("food", 0) or 0)
    if legacy > 0:
        pet_st = progress.get("pet_state") if isinstance(progress.get("pet_state"), dict) else {}
        pt = str((pet_st or {}).get("type") or "cat")
        if pt not in _PET_TYPES:
            pt = "cat"
        ft[pt] = int(ft.get(pt, 0) or 0) + legacy
        inv["food"] = 0
    inv["food_by_type"] = ft
    inv.setdefault("toy", int(inv.get("toy", 0) or 0))
    progress["inventory"] = inv
    return inv


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_session(authorization: str) -> tuple[str, dict]:
    token = authorization.replace("Bearer ", "")
    session = sessions.get(token)
    if session is None:
        raise api_error(401, "unauthorized")
    other = ensure_gameshub_schema(session.user.get("other_data") or {})
    session.user["other_data"] = other
    games = other.setdefault("games", {})
    progress = games.get(settings.tamagochi_game_key)
    if not isinstance(progress, dict):
        progress = {"playtime": 0}
        games[settings.tamagochi_game_key] = progress
    progress.setdefault("pet_history", [])
    return token, progress


def _save_progress(token: str, progress: dict, *, now: datetime) -> None:
    username = sessions[token].username
    pet = progress.get("pet_state")
    neglect = progress.get("neglect") or {}
    if isinstance(pet, dict):
        ensure_death_archived(progress, pet, owner_username=username, neglect=neglect, now=now)
    users_api.save_user(sessions[token].user)


class AdoptRequest(BaseModel):
    type: PetType
    pet_name: Optional[str] = Field(default=None, max_length=32)


class ActionRequest(BaseModel):
    type: ActionType
    payload: dict | None = None


@router.get("/shop")
def shop(authorization: str = Header(default="")) -> dict:
    now = _now()
    token, progress = _get_session(authorization)
    other = ensure_gameshub_schema(sessions[token].user.get("other_data") or {})
    sessions[token].user["other_data"] = other
    prices = get_shop_prices(now)
    diamonds = int(other.get("diamonds", 0))
    coins = int(progress.get("coins", 0) or 0)
    inv = _migrate_inventory(progress)
    return {
        "prices": {
            "food_diamonds": prices.food_diamonds,
            "toy_diamonds": prices.toy_diamonds,
            "diamonds_to_coins_rate": prices.diamonds_to_coins_rate,
        },
        "effects": item_effects_doc(),
        "wallet": {"diamonds": diamonds, "coins": coins},
        "inventory": {"food_by_type": dict(inv.get("food_by_type") or {}), "toy": int(inv.get("toy", 0) or 0)},
    }


class ExchangeRequest(BaseModel):
    diamonds: int = Field(ge=1, le=10_000)


@router.post("/exchange")
def exchange(payload: ExchangeRequest, authorization: str = Header(default="")) -> dict:
    now = _now()
    token, progress = _get_session(authorization)
    other = ensure_gameshub_schema(sessions[token].user.get("other_data") or {})
    sessions[token].user["other_data"] = other
    prices = get_shop_prices(now)

    diamonds = int(other.get("diamonds", 0))
    if diamonds < payload.diamonds:
        raise api_error(400, "insufficient_diamonds", params={"required": payload.diamonds})
    other["diamonds"] = diamonds - int(payload.diamonds)

    coins = int(progress.get("coins", 0) or 0)
    coins += int(payload.diamonds) * int(prices.diamonds_to_coins_rate)
    progress["coins"] = coins
    users_api.save_user(sessions[token].user)
    return {"ok": True, "wallet": {"diamonds": int(other["diamonds"]), "coins": coins}}


class BuyRequest(BaseModel):
    item: str = Field(min_length=1, max_length=32)  # food|toy
    qty: int = Field(ge=1, le=100)
    food_for: Optional[PetType] = None


@router.post("/buy")
def buy(payload: BuyRequest, authorization: str = Header(default="")) -> dict:
    now = _now()
    token, progress = _get_session(authorization)
    other = ensure_gameshub_schema(sessions[token].user.get("other_data") or {})
    sessions[token].user["other_data"] = other
    prices = get_shop_prices(now)

    item = payload.item
    if item not in ("food", "toy"):
        raise api_error(400, "unknown_item")

    # We price in diamonds but settle via internal coins by exchange; to keep it simple:
    # buy requires coins, cost is diamonds_price * rate coins per diamond.
    coins = int(progress.get("coins", 0) or 0)
    if item == "food":
        cost_d = prices.food_diamonds
    else:
        cost_d = prices.toy_diamonds
    cost_coins = int(cost_d) * int(prices.diamonds_to_coins_rate) * int(payload.qty)
    if coins < cost_coins:
        raise api_error(400, "insufficient_coins", params={"required": cost_coins})

    inv = _migrate_inventory(progress)
    if item == "food":
        if payload.food_for is None:
            raise api_error(400, "food_for_required")
        k = payload.food_for
        ft = inv.setdefault("food_by_type", {})
        if not isinstance(ft, dict):
            ft = {}
            inv["food_by_type"] = ft
        ft[k] = int(ft.get(k, 0) or 0) + int(payload.qty)
    else:
        inv["toy"] = int(inv.get("toy", 0) or 0) + int(payload.qty)
    progress["inventory"] = inv
    progress["coins"] = coins - cost_coins

    # buying toy also extends a global toy buff duration (passive)
    if item == "toy":
        # 24h per toy, stacked
        cur = progress.get("toy_until")
        base = now
        if isinstance(cur, str):
            try:
                parsed = datetime.fromisoformat(cur.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                if parsed > base:
                    base = parsed
            except Exception:
                pass
        progress["toy_until"] = (base + timedelta(hours=2 * int(payload.qty))).isoformat()
        # diamond boost: 10 minutes per toy, stacked (short buff)
        cur2 = progress.get("toy_diamond_until")
        base2 = now
        if isinstance(cur2, str):
            try:
                parsed2 = datetime.fromisoformat(cur2.replace("Z", "+00:00"))
                if parsed2.tzinfo is None:
                    parsed2 = parsed2.replace(tzinfo=timezone.utc)
                if parsed2 > base2:
                    base2 = parsed2
            except Exception:
                pass
        progress["toy_diamond_until"] = (base2 + timedelta(minutes=20 * int(payload.qty))).isoformat()

    pet_st = progress.get("pet_state")
    if isinstance(pet_st, dict) and item == "toy":
        merge_shop_toy_buffs_from_progress(progress, pet_st)

    users_api.save_user(sessions[token].user)
    return {"ok": True, "inventory": inv, "wallet": {"coins": int(progress["coins"]), "diamonds": int(other.get("diamonds", 0))}}


@router.get("/me")
def me(authorization: str = Header(default="")) -> dict:
    now = _now()
    token, progress = _get_session(authorization)

    pet = progress.get("pet_state")
    neglect = progress.get("neglect") or {}

    if isinstance(pet, dict) and pet.get("alive", True):
        pet_state = pet  # type: ignore[assignment]
        merge_shop_toy_buffs_from_progress(progress, pet_state)
        res = sync_pet_state(pet_state, neglect, now=now, offline=True)
        pet_state = res.pet
        neglect = res.neglect
        # entering the game counts as a visit (for neglect mechanics)
        neglect = register_visit(neglect, now=now, pet_is_critical=is_critical(pet_state))
        progress["pet_state"] = pet_state
        progress["neglect"] = neglect
        progress["last_update_at"] = pet_state.get("last_update_at")
        _save_progress(token, progress, now=now)
        return {"pet": pet_state, "neglect": neglect}

    # no pet or dead
    return {"pet": None, "neglect": neglect}


@router.get("/status")
def status(authorization: str = Header(default="")) -> dict:
    """Lightweight hub reminder check."""
    now = _now()
    token, progress = _get_session(authorization)
    pet = progress.get("pet_state")
    neglect = progress.get("neglect") or {}
    if isinstance(pet, dict) and pet.get("alive", True):
        merge_shop_toy_buffs_from_progress(progress, pet)
        res = sync_pet_state(pet, neglect, now=now, offline=True)
        pet = res.pet
        neglect = res.neglect
        progress["pet_state"] = pet
        progress["neglect"] = neglect
        _save_progress(token, progress, now=now)
    attn = pet_needs_attention(pet if isinstance(pet, dict) else None, now=now)
    return attn


@router.get("/history")
def history(authorization: str = Header(default="")) -> dict:
    _, progress = _get_session(authorization)
    hist = progress.get("pet_history")
    if not isinstance(hist, list):
        hist = []
    return {"history": list(reversed(hist[-50:]))}


class RecreateRequest(BaseModel):
    type: PetType
    pet_name: Optional[str] = Field(default=None, max_length=32)


@router.post("/recreate")
def recreate(payload: RecreateRequest, authorization: str = Header(default="")) -> dict:
    now = _now()
    token, progress = _get_session(authorization)
    username = sessions[token].username

    coins_avail = int(progress.get("coins", 0) or 0)
    if coins_avail < RECREATE_PET_COINS_COST:
        raise api_error(400, "insufficient_coins", params={"required": RECREATE_PET_COINS_COST})
    progress["coins"] = coins_avail - RECREATE_PET_COINS_COST

    pet = progress.get("pet_state")
    neglect = progress.get("neglect") or {}
    if isinstance(pet, dict) and pet.get("alive", True):
        merge_shop_toy_buffs_from_progress(progress, pet)
        res = sync_pet_state(pet, neglect, now=now, offline=True)
        pet = res.pet
        archive_pet(progress, pet, owner_username=username, reason="recreated", now=now, neglect=res.neglect)
    pet_id = uuid4().hex
    new_pet: PetState = make_new_pet(payload.type, now=now, pet_id=pet_id, pet_name=payload.pet_name)
    progress["pet_state"] = new_pet
    progress["pet"] = {"type": payload.type, "pet_id": pet_id}
    progress["last_update_at"] = new_pet.get("last_update_at")
    progress["neglect"] = {"strikes": 0, "critical_ignored_seconds": 0, "last_critical_seen_at": None, "visit": {}}
    sessions[token].user["other_data"] = ensure_gameshub_schema(sessions[token].user.get("other_data") or {})
    _save_progress(token, progress, now=now)
    # If WS is already connected, the world keeps in-memory pet state for connected owners
    # and won't refresh it from users_api. Force-refresh immediately so map/avatar updates.
    tamagochi_world.connect_owner(username, new_pet, progress.get("neglect") if isinstance(progress, dict) else None, now=now)
    return {"ok": True, "pet": new_pet}


@router.post("/adopt")
def adopt(payload: AdoptRequest, authorization: str = Header(default="")) -> dict:
    now = _now()
    token, progress = _get_session(authorization)
    username = sessions[token].username

    pet = progress.get("pet_state")
    if isinstance(pet, dict) and pet.get("alive", True):
        return {"pet": pet, "ok": True}

    pet_id = uuid4().hex
    new_pet: PetState = make_new_pet(payload.type, now=now, pet_id=pet_id, pet_name=payload.pet_name)
    progress["pet_state"] = new_pet
    progress["pet"] = {"type": payload.type, "pet_id": pet_id}
    progress["last_update_at"] = new_pet.get("last_update_at")
    progress["neglect"] = {"strikes": 0, "critical_ignored_seconds": 0, "last_critical_seen_at": None, "visit": {}}

    sessions[token].user["other_data"] = ensure_gameshub_schema(sessions[token].user.get("other_data") or {})
    _save_progress(token, progress, now=now)
    # Same as recreate: if user is already in the WS world, update immediately.
    tamagochi_world.connect_owner(username, new_pet, progress.get("neglect") if isinstance(progress, dict) else None, now=now)
    return {"ok": True, "pet": new_pet}


@router.post("/action")
def action(payload: ActionRequest, authorization: str = Header(default="")) -> dict:
    now = _now()
    token, progress = _get_session(authorization)

    pet = progress.get("pet_state")
    neglect = progress.get("neglect") or {}
    if not isinstance(pet, dict) or not pet.get("alive", True):
        raise api_error(400, "no_active_pet")

    pet_state: PetState = pet  # type: ignore[assignment]
    merge_shop_toy_buffs_from_progress(progress, pet_state)
    # sync before applying action
    res = sync_pet_state(pet_state, neglect, now=now, offline=True)
    pet_state, neglect = res.pet, res.neglect

    # feed requires food in inventory (matching pet type)
    if payload.type == "feed":
        inv = _migrate_inventory(progress)
        pt = str(pet_state.get("type") or "cat")
        ft = inv.get("food_by_type") or {}
        if int(ft.get(pt, 0) or 0) <= 0:
            raise api_error(400, "need_food")
        ft[pt] = int(ft.get(pt, 0) or 0) - 1
        progress["inventory"] = inv
        pet_state.setdefault("buffs", {})
        # well-fed for ~7 hours (covers ~5-10h target with current hunger rate)
        pet_state["buffs"]["well_fed_until"] = (now + timedelta(hours=7)).isoformat()

    coin_cost = 0
    if payload.type == "play":
        coin_cost = PLAY_ACTION_COINS_COST
    elif payload.type == "sleep":
        coin_cost = SLEEP_ACTION_COINS_COST
    if coin_cost:
        coins_avail = int(progress.get("coins", 0) or 0)
        if coins_avail < coin_cost:
            raise api_error(400, "insufficient_coins", params={"required": coin_cost})

    result = apply_action(pet_state, payload.type, payload.payload, now=now)
    if not result.ok:
        raise api_error(400, "action_failed", message=result.reason or "Action failed")

    tamagochi_world.interrupt_diamond_search_if_active(pet_state, sessions[token].username, now=now)

    if payload.type in ("feed", "play", "sleep", "wake"):
        neglect = register_useful_action(neglect, now=now)

    if coin_cost:
        progress["coins"] = int(progress.get("coins", 0) or 0) - coin_cost

    merge_shop_toy_buffs_from_progress(progress, pet_state)

    progress["pet_state"] = pet_state
    progress["neglect"] = neglect
    progress["last_update_at"] = pet_state.get("last_update_at")

    _save_progress(token, progress, now=now)
    return {"ok": True, "pet": pet_state, "neglect": neglect}


@router.post("/heal_coins")
def heal_coins(authorization: str = Header(default="")) -> dict:
    """+10% здоровья за монеты (сырые пункты HP 0..100)."""
    now = _now()
    token, progress = _get_session(authorization)

    pet = progress.get("pet_state")
    neglect = progress.get("neglect") or {}
    if not isinstance(pet, dict) or not pet.get("alive", True):
        raise api_error(400, "no_active_pet")

    pet_state: PetState = pet  # type: ignore[assignment]
    res = sync_pet_state(pet_state, neglect, now=now, offline=True)
    pet_state, neglect = res.pet, res.neglect

    stats = pet_state.setdefault("stats", {})
    hp = int(stats.get("hp", 100))
    if hp >= 100:
        raise api_error(400, "health_full")

    coins = int(progress.get("coins", 0) or 0)
    if coins < HEAL_COINS_COST:
        raise api_error(400, "insufficient_coins", params={"required": HEAL_COINS_COST})

    stats["hp"] = min(100, hp + HEAL_HP_POINTS)
    pet_state["stats"] = stats
    progress["pet_state"] = pet_state
    progress["coins"] = coins - HEAL_COINS_COST
    progress["last_update_at"] = pet_state.get("last_update_at")

    tamagochi_world.interrupt_diamond_search_if_active(pet_state, sessions[token].username, now=now)
    neglect = register_useful_action(neglect, now=now)
    progress["neglect"] = neglect

    _save_progress(token, progress, now=now)
    other = ensure_gameshub_schema(sessions[token].user.get("other_data") or {})
    return {
        "ok": True,
        "pet": pet_state,
        "neglect": neglect,
        "wallet": {"coins": int(progress["coins"]), "diamonds": int(other.get("diamonds", 0))},
    }


class EndVisitRequest(BaseModel):
    ended_at: datetime = Field(default_factory=_now)


@router.post("/end_visit")
def end_visit(payload: EndVisitRequest, authorization: str = Header(default="")) -> dict:
    """
    Called by frontend when player leaves the game view.
    Used only for neglect-strike accounting.
    """
    now = _now()
    token, progress = _get_session(authorization)

    pet = progress.get("pet_state")
    neglect = progress.get("neglect") or {}
    if not isinstance(pet, dict):
        return {"ok": True}

    pet_state: PetState = pet  # type: ignore[assignment]
    ended_at = payload.ended_at
    if ended_at.tzinfo is None:
        ended_at = ended_at.replace(tzinfo=timezone.utc)
    neglect = maybe_add_neglect_strike(pet_state, neglect, now=now, visit_ended_at=ended_at)
    progress["neglect"] = neglect
    _save_progress(token, progress, now=now)
    return {"ok": True, "neglect": neglect, "alive": bool(pet_state.get("alive", True))}

