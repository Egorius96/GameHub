from __future__ import annotations

from datetime import datetime
from typing import Any

from app.games.tamagochi_world.constants import TUNING
from app.games.tamagochi_world.timeutils import iso_utc, parse_dt

PET_HISTORY_MAX = 50
DIAMOND_BEST_COOLDOWN_NEW_SEC = 120.0
DIAMOND_BEST_COOLDOWN_MATURE_SEC = 60.0
DIAMOND_AGE_MATURE_DAYS = 90.0


def pet_age_seconds(pet: dict[str, Any], *, now: datetime) -> float:
    created = parse_dt(pet.get("created_at")) or parse_dt(pet.get("last_update_at"))
    if created is None:
        return 0.0
    return max(0.0, (now - created).total_seconds())


def pet_age_days(pet: dict[str, Any], *, now: datetime) -> float:
    return pet_age_seconds(pet, now=now) / 86400.0


def diamond_age_cooldown_multiplier(pet: dict[str, Any], *, now: datetime) -> float:
    """1.0 for new pet (~2 min best), ~0.5 at 90+ days (~1 min best)."""
    days = pet_age_days(pet, now=now)
    t = min(1.0, days / DIAMOND_AGE_MATURE_DAYS)
    return 1.0 - 0.5 * t


def estimate_best_diamond_interval_minutes(pet: dict[str, Any], *, now: datetime, wellbeing_factor: float = 1.0) -> float:
    days = pet_age_days(pet, now=now)
    t = min(1.0, days / DIAMOND_AGE_MATURE_DAYS)
    target_median = DIAMOND_BEST_COOLDOWN_NEW_SEC * (1.0 - t) + DIAMOND_BEST_COOLDOWN_MATURE_SEC * t
    base_median = float(TUNING.diamond_cooldown_min_sec) + float(TUNING.diamond_cooldown_rand_span_sec) / 2.0
    age_mult = diamond_age_cooldown_multiplier(pet, now=now)
    return round((base_median * age_mult * wellbeing_factor * target_median / DIAMOND_BEST_COOLDOWN_NEW_SEC) / 60.0, 1)


def _death_reason_from_neglect(neglect: dict[str, Any]) -> str:
    ignored = int(neglect.get("critical_ignored_seconds", 0) or 0)
    strikes = int(neglect.get("strikes", 0) or 0)
    if strikes >= int(getattr(TUNING, "neglect_strikes_required", 3)) and ignored >= int(TUNING.neglect_dead_after.total_seconds()):
        return "neglect"
    return "hunger"


def archive_pet(
    progress: dict[str, Any],
    pet: dict[str, Any],
    *,
    owner_username: str,
    reason: str,
    now: datetime,
    neglect: dict[str, Any] | None = None,
) -> None:
    if not isinstance(pet, dict):
        return
    history = progress.get("pet_history")
    if not isinstance(history, list):
        history = []
    created = parse_dt(pet.get("created_at")) or parse_dt(pet.get("last_update_at"))
    age_sec = int(pet_age_seconds(pet, now=now)) if created else 0
    final_reason = reason
    if reason == "neglect" and neglect:
        final_reason = _death_reason_from_neglect(neglect)
    entry = {
        "pet_id": str(pet.get("pet_id") or ""),
        "pet_name": str(pet.get("pet_name") or "").strip() or None,
        "type": pet.get("type"),
        "owner_username": owner_username,
        "created_at": iso_utc(created) if created else None,
        "ended_at": iso_utc(now),
        "age_seconds": age_sec,
        "reason": final_reason,
    }
    history.append(entry)
    progress["pet_history"] = history[-PET_HISTORY_MAX:]


def ensure_death_archived(
    progress: dict[str, Any],
    pet: dict[str, Any],
    *,
    owner_username: str,
    neglect: dict[str, Any],
    now: datetime,
) -> None:
    if not isinstance(pet, dict) or pet.get("alive", True):
        return
    archived = progress.get("_archived_pet_ids")
    if not isinstance(archived, list):
        archived = []
    pid = str(pet.get("pet_id") or "")
    if not pid or pid in archived:
        return
    archive_pet(progress, pet, owner_username=owner_username, reason="neglect", now=now, neglect=neglect)
    archived.append(pid)
    progress["_archived_pet_ids"] = archived[-60:]


def pet_needs_attention(pet: dict[str, Any] | None, *, now: datetime) -> dict[str, Any]:
    if not isinstance(pet, dict) or not pet.get("alive", True):
        return {"needs_attention": False, "reason": None}
    stats = pet.get("stats") or {}
    hunger = int(stats.get("hunger", 0))
    hp = int(stats.get("hp", 100))
    if hunger >= TUNING.hunger_crit or hp <= TUNING.hp_crit:
        return {"needs_attention": True, "reason": "critical"}
    if hunger >= max(70, TUNING.hunger_crit - 10) or hp <= max(30, TUNING.hp_crit + 10):
        return {"needs_attention": True, "reason": "hungry"}
    return {"needs_attention": False, "reason": None}
