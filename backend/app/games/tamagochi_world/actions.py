from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional, TypedDict, cast

from .constants import TUNING
from .pet_state import PetState, PetStats, clamp_int


class MoveToPayload(TypedDict):
    x: float
    y: float


ActionType = Literal["feed", "play", "sleep", "wake", "move_to"]


@dataclass(slots=True)
class ActionResult:
    ok: bool
    reason: Optional[str] = None


def apply_action(pet: PetState, action: ActionType, payload: dict | None, *, now: datetime) -> ActionResult:
    if not pet.get("alive", True):
        return ActionResult(ok=False, reason="pet_dead")

    if action == "sleep":
        if pet.get("is_sleeping", False):
            return ActionResult(ok=False, reason="already_sleeping")
        pet["is_sleeping"] = True
        pet["target"] = None
        pet.pop("wander_dest", None)
        return ActionResult(ok=True)

    if action == "wake":
        pet["is_sleeping"] = False
        pet.pop("wander_paused_until", None)
        pet.pop("wander_dest", None)
        return ActionResult(ok=True)

    if action == "move_to":
        if pet.get("is_sleeping", False):
            return ActionResult(ok=False, reason="pet_sleeping")
        if not isinstance(payload, dict):
            return ActionResult(ok=False, reason="bad_payload")
        try:
            x = float(payload.get("x"))
            y = float(payload.get("y"))
        except Exception:
            return ActionResult(ok=False, reason="bad_payload")
        x = max(0.0, min(TUNING.world_w, x))
        y = max(0.0, min(TUNING.world_h, y))
        pet["target"] = {"x": x, "y": y}
        pet.pop("wander_paused_until", None)
        pet.pop("wander_dest", None)
        return ActionResult(ok=True)

    stats = pet.get("stats") or {}
    stats = cast(PetStats, stats)

    if action == "feed":
        stats["hunger"] = clamp_int(int(stats.get("hunger", 0)) + TUNING.feed_hunger_delta)
        stats["mood"] = clamp_int(int(stats.get("mood", 50)) + TUNING.feed_mood_delta)
        stats["sleepiness"] = clamp_int(int(stats.get("sleepiness", 0)) + TUNING.feed_sleepiness_delta)
        pet["stats"] = stats
        return ActionResult(ok=True)

    if action == "play":
        if pet.get("is_sleeping", False):
            return ActionResult(ok=False, reason="pet_sleeping")
        stats["mood"] = clamp_int(int(stats.get("mood", 50)) + TUNING.owner_play_mood_delta)
        stats["hunger"] = clamp_int(int(stats.get("hunger", 0)) + TUNING.owner_play_hunger_delta)
        stats["sleepiness"] = clamp_int(int(stats.get("sleepiness", 0)) + TUNING.owner_play_sleepiness_delta)
        pet["stats"] = stats
        return ActionResult(ok=True)

    return ActionResult(ok=False, reason="unknown_action")

