from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Optional, TypedDict, cast

from .constants import ACTIVITY_ENERGY_DRAIN_MULT, TUNING
from .timeutils import iso_utc, parse_dt


PetType = Literal["cat", "dog", "pokemon", "capybara", "alien"]


class Vec2(TypedDict):
    x: float
    y: float


class PetStats(TypedDict):
    hp: int  # 0..100
    hunger: int  # 0..100 (0 full, 100 hungry)
    sleepiness: int  # 0..100 (0 бодр, 100 спать)
    mood: int  # 0..100 (0 грустно, 100 весело)


class PetState(TypedDict, total=False):
    pet_id: str
    type: PetType
    alive: bool
    is_sleeping: bool
    pos: Vec2
    target: Optional[Vec2]
    wander_dest: Optional[Vec2]
    wander_gen: int
    stats: PetStats
    last_update_at: str  # iso utc
    buffs: dict


class VisitState(TypedDict, total=False):
    started_at: str
    last_strike_at: Optional[str]
    in_critical_at_entry: bool
    useful_action_at: Optional[str]


class NeglectState(TypedDict, total=False):
    strikes: int
    critical_ignored_seconds: int
    last_critical_seen_at: Optional[str]
    visit: VisitState


class GameProgress(TypedDict, total=False):
    playtime: int
    pet: Optional[dict]
    pet_state: Optional[PetState]
    last_update_at: Optional[str]


def merge_shop_toy_buffs_from_progress(progress: dict, pet: PetState) -> None:
    """Синхронизировать buffs питомца с полями прогресса магазина (игрушка куплена, WS без /action)."""
    if not isinstance(progress, dict) or not isinstance(pet, dict):
        return
    tu = progress.get("toy_until")
    td = progress.get("toy_diamond_until")
    pet.setdefault("buffs", {})
    b = pet.get("buffs")
    if not isinstance(b, dict):
        b = {}
        pet["buffs"] = b
    if isinstance(tu, str):
        b["toy_until"] = tu
    else:
        b.pop("toy_until", None)
    if isinstance(td, str):
        b["toy_diamond_until"] = td
    else:
        b.pop("toy_diamond_until", None)


def clamp_int(v: float | int, lo: int = 0, hi: int = 100) -> int:
    try:
        n = int(round(float(v)))
    except Exception:
        n = lo
    return max(lo, min(hi, n))


def _hash_u32(*parts: str) -> int:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8", errors="ignore"))
        h.update(b"|")
    return int.from_bytes(h.digest()[:4], "big", signed=False)


def _baseline_awake_sleepiness_rate() -> float:
    h = float(TUNING.energy_drain_baseline_hours)
    return 100.0 / (h * 3600.0)


def _sleep_recovery_rate() -> float:
    return 100.0 / (float(TUNING.energy_recovery_hours_full) * 3600.0)


def _awake_sleepiness_rate(hp: float, hunger: float, mood: float, activity: str) -> float:
    base = _baseline_awake_sleepiness_rate()
    am = float(ACTIVITY_ENERGY_DRAIN_MULT.get(activity, ACTIVITY_ENERGY_DRAIN_MULT["__default__"]))
    hp_f = max(0.0, min(100.0, hp))
    hun_f = max(0.0, min(100.0, hunger))
    mood_f = max(0.0, min(100.0, mood))
    stress = (
        (1.0 + float(TUNING.drain_stress_hp_weight) * (1.0 - hp_f / 100.0))
        * (1.0 + float(TUNING.drain_stress_hunger_weight) * (hun_f / 100.0))
        * (1.0 + float(TUNING.drain_stress_mood_weight) * (1.0 - mood_f / 100.0))
    )
    raw = base * am * stress
    lo = 100.0 / (float(TUNING.energy_drain_hours_max) * 3600.0)
    hi = 100.0 / (float(TUNING.energy_drain_hours_min) * 3600.0)
    return max(lo, min(hi, raw))


def is_critical(pet: PetState) -> bool:
    stats = pet.get("stats") or {}
    hunger = int(stats.get("hunger", 0))
    hp = int(stats.get("hp", 100))
    return hunger >= TUNING.hunger_crit or hp <= TUNING.hp_crit


def make_new_pet(pet_type: PetType, *, now: datetime, pet_id: str) -> PetState:
    # spawn stable-ish but not identical by type+id
    seed = _hash_u32(pet_id, pet_type)
    x = float(120 + (seed % int(TUNING.world_w - 240)))
    y = float(120 + ((seed // 97) % int(TUNING.world_h - 240)))
    return {
        "pet_id": pet_id,
        "type": pet_type,
        "alive": True,
        "is_sleeping": False,
        "pos": {"x": x, "y": y},
        "target": None,
        "stats": {"hp": 100, "hunger": 20, "sleepiness": 10, "mood": 70},
        "last_update_at": iso_utc(now),
    }


@dataclass(slots=True)
class SimResult:
    pet: PetState
    neglect: NeglectState


def sync_pet_state(
    pet: PetState,
    neglect: NeglectState,
    *,
    now: datetime,
    offline: bool,
) -> SimResult:
    """
    Applies deterministic simulation from pet.last_update_at to now.
    Offline: time goes slower, hunger/hp clamp at critical floors.
    Neglect: tracks "ignored in critical" seconds and can kill pet.
    """
    if not pet.get("alive", True):
        pet["last_update_at"] = iso_utc(now)
        return SimResult(pet=pet, neglect=neglect)

    last = parse_dt(pet.get("last_update_at"))
    if last is None:
        last = now
        pet["last_update_at"] = iso_utc(now)
        return SimResult(pet=pet, neglect=neglect)

    if now <= last:
        return SimResult(pet=pet, neglect=neglect)

    dt_real = (now - last).total_seconds()
    if dt_real <= 0:
        return SimResult(pet=pet, neglect=neglect)

    dt = dt_real * (TUNING.offline_rate if offline else 1.0)
    dt = min(dt, 60 * 60 * 12)  # cap 12h effective to avoid huge jumps in one call

    stats = cast(PetStats, pet.get("stats") or {})
    hp = float(stats.get("hp", 100))
    hunger = float(stats.get("hunger", 0))
    sleepiness = float(stats.get("sleepiness", 0))
    mood = float(stats.get("mood", 50))
    sleeping = bool(pet.get("is_sleeping", False))
    activity_code = str(pet.get("activity") or "wandering")
    buffs = pet.get("buffs") or {}
    if not isinstance(buffs, dict):
        buffs = {}
    well_fed_until = parse_dt(buffs.get("well_fed_until"))
    toy_until = parse_dt(buffs.get("toy_until"))

    # Голод: во сне ниже базальный расход энергии с едой; HP и настроение влияют на аппетит
    hunger_rate = float(TUNING.hunger_per_sec) * (float(TUNING.hunger_sleep_mult) if sleeping else 1.0)
    if well_fed_until is not None and now < well_fed_until:
        hunger_rate *= 0.35
    hunger_rate *= 1.0 - float(TUNING.hunger_hp_low_appetite) * (1.0 - max(0.0, min(100.0, hp)) / 100.0)
    if mood < 50.0:
        hunger_rate *= 1.0 + float(TUNING.hunger_mood_stress_eat) * ((50.0 - mood) / 50.0)
    hunger += hunger_rate * dt

    # Бодрость (сонливость ↑ бодрствуя, ↓ во сне за ~energy_recovery_hours_full часов полный цикл)
    if sleeping:
        sleepiness -= _sleep_recovery_rate() * dt
    else:
        sleepiness += _awake_sleepiness_rate(hp, hunger, mood, activity_code) * dt
        if sleepiness >= 100.0:
            sleepiness = 100.0
            sleeping = True
            pet["is_sleeping"] = True

    # mood baseline decay (faster when uncomfortable)
    mood_penalty = 1.0
    if hunger >= TUNING.hunger_crit:
        mood_penalty += 0.8
    if sleepiness >= TUNING.sleepiness_crit:
        mood_penalty += 0.5
    if hp <= TUNING.hp_crit:
        mood_penalty += 0.7
    mood_decay = TUNING.mood_down_per_sec * dt * mood_penalty
    if toy_until is not None and now < toy_until:
        mood_decay *= 0.85
    if hunger < 35.0:
        mood_decay *= 0.92
    mood -= mood_decay

    # hp dynamics
    if not offline:
        if hunger >= TUNING.hunger_crit:
            hp -= TUNING.hp_down_per_sec_on_crit_hunger * dt
        if sleepiness >= TUNING.sleepiness_crit:
            hp -= TUNING.hp_down_per_sec_on_crit_sleep * dt
    if sleeping and hunger < TUNING.hunger_crit:
        hp += TUNING.hp_up_per_sec_sleeping * dt

    # clamps
    if offline:
        hunger = min(hunger, float(TUNING.hunger_crit))
        hp = max(hp, float(TUNING.hp_crit))
    hp = float(clamp_int(hp))
    hunger = float(clamp_int(hunger))
    sleepiness = float(clamp_int(sleepiness))
    mood = float(clamp_int(mood))

    # Полная бодрость (сонливость 0) — просыпается само
    if sleeping and int(sleepiness) <= 0:
        sleeping = False
        pet["is_sleeping"] = False
        sleepiness = 0.0

    pet["is_sleeping"] = bool(sleeping)

    stats["hp"] = int(hp)
    stats["hunger"] = int(hunger)
    stats["sleepiness"] = int(sleepiness)
    stats["mood"] = int(mood)
    pet["stats"] = stats
    pet["buffs"] = buffs

    # movement (deterministic wander when no target)
    pos = cast(Vec2, pet.get("pos") or {"x": 0.0, "y": 0.0})
    pos_x = float(pos.get("x", 0.0))
    pos_y = float(pos.get("y", 0.0))

    if not sleeping:
        pause_until = parse_dt(pet.get("wander_paused_until"))
        target = pet.get("target")
        if target and isinstance(target, dict):
            tx = float(target.get("x", pos_x))
            ty = float(target.get("y", pos_y))
            dx = tx - pos_x
            dy = ty - pos_y
            dist = (dx * dx + dy * dy) ** 0.5
            if dist <= float(TUNING.arrival_distance_px):
                pet["target"] = None
                pet["wander_paused_until"] = iso_utc(now + TUNING.wander_resume_after_command)
                pet.pop("wander_dest", None)
            elif dist > 1e-6:
                step = min(dist, TUNING.pet_speed * dt)
                pos_x += dx / dist * step
                pos_y += dy / dist * step
        else:
            if pause_until is not None and now < pause_until:
                pass
            else:
                pet.pop("wander_paused_until", None)
                pet_id = str(pet.get("pet_id", "pet"))
                margin = float(TUNING.wander_margin_px)
                span_w = max(80.0, float(TUNING.world_w) - 2.0 * margin)
                span_h = max(80.0, float(TUNING.world_h) - 2.0 * margin)
                wd_raw = pet.get("wander_dest")
                wd: dict[str, float] | None = wd_raw if isinstance(wd_raw, dict) else None
                if wd is None:
                    wg = int(pet.get("wander_gen", 0) or 0) + 1
                    pet["wander_gen"] = wg
                    last_s = iso_utc(last)
                    # Два отдельных хеша: из одного u32 нельзя честно получить обе координаты
                    # (частное seed // N остаётся << span_h), иначе цели скапливаются у «верха» карты.
                    seed_x = _hash_u32(pet_id, "wander_dest_x", str(wg), last_s)
                    seed_y = _hash_u32(pet_id, "wander_dest_y", str(wg), last_s)
                    tx = margin + float(seed_x % max(1, int(span_w)))
                    ty = margin + float(seed_y % max(1, int(span_h)))
                    wd = {"x": tx, "y": ty}
                    pet["wander_dest"] = wd
                tx = float(wd.get("x", pos_x))
                ty = float(wd.get("y", pos_y))
                dx = tx - pos_x
                dy = ty - pos_y
                dist = (dx * dx + dy * dy) ** 0.5
                if dist <= float(TUNING.arrival_distance_px):
                    pet.pop("wander_dest", None)
                elif dist > 1e-6:
                    step = min(dist, TUNING.pet_speed * dt)
                    pos_x += dx / dist * step
                    pos_y += dy / dist * step

    pos_x = max(0.0, min(TUNING.world_w, pos_x))
    pos_y = max(0.0, min(TUNING.world_h, pos_y))
    pet["pos"] = {"x": pos_x, "y": pos_y}

    # neglect clock & death by repeated ignoring
    _apply_neglect_clock(pet, neglect, now=now, dt_real_seconds=int(dt_real))

    pet["last_update_at"] = iso_utc(now)
    return SimResult(pet=pet, neglect=neglect)


def _apply_neglect_clock(pet: PetState, neglect: NeglectState, *, now: datetime, dt_real_seconds: int) -> None:
    if not pet.get("alive", True):
        return

    stats = pet.get("stats") or {}
    hunger = int(stats.get("hunger", 0))
    hp = int(stats.get("hp", 100))
    critical = hunger >= TUNING.hunger_crit or hp <= TUNING.hp_crit

    if not critical:
        neglect["last_critical_seen_at"] = None
        return

    # if in critical and no useful action registered in current visit, accumulate ignored time
    visit = neglect.get("visit") or {}
    useful_at = parse_dt(visit.get("useful_action_at"))
    started_at = parse_dt(visit.get("started_at"))
    if started_at is not None and useful_at is None:
        cur = int(neglect.get("critical_ignored_seconds", 0) or 0)
        neglect["critical_ignored_seconds"] = cur + max(0, int(dt_real_seconds))

    last_seen = parse_dt(neglect.get("last_critical_seen_at"))
    if last_seen is None:
        neglect["last_critical_seen_at"] = iso_utc(now)

    strikes = int(neglect.get("strikes", 0) or 0)
    ignored = int(neglect.get("critical_ignored_seconds", 0) or 0)
    if strikes >= int(getattr(TUNING, "neglect_strikes_required", 3)) and ignored >= int(TUNING.neglect_dead_after.total_seconds()):
        pet["alive"] = False


def register_visit(neglect: NeglectState, *, now: datetime, pet_is_critical: bool) -> NeglectState:
    visit = neglect.get("visit") or {}
    visit["started_at"] = iso_utc(now)
    visit["in_critical_at_entry"] = bool(pet_is_critical)
    visit.setdefault("last_strike_at", neglect.get("last_critical_seen_at"))
    visit["useful_action_at"] = None
    neglect["visit"] = visit
    return neglect


def register_useful_action(neglect: NeglectState, *, now: datetime) -> NeglectState:
    visit = neglect.get("visit") or {}
    visit["useful_action_at"] = iso_utc(now)
    neglect["visit"] = visit
    # doing something useful clears critical ignored time pressure
    neglect["critical_ignored_seconds"] = 0
    neglect["last_critical_seen_at"] = None
    strikes = int(neglect.get("strikes", 0) or 0)
    neglect["strikes"] = max(0, strikes - 1)
    return neglect


def maybe_add_neglect_strike(
    pet: PetState,
    neglect: NeglectState,
    *,
    now: datetime,
    visit_ended_at: datetime,
) -> NeglectState:
    """
    Called when a visit/session ends (disconnect/leave view).
    If player saw critical pet and did nothing useful during grace window, add a strike.
    """
    if not pet.get("alive", True):
        return neglect

    visit = neglect.get("visit") or {}
    started_at = parse_dt(visit.get("started_at"))
    useful_at = parse_dt(visit.get("useful_action_at"))
    in_crit = bool(visit.get("in_critical_at_entry", False))
    if not started_at or not in_crit:
        return neglect

    if useful_at is not None:
        return neglect

    if visit_ended_at - started_at <= TUNING.grace_window:
        # user left too quickly: do not count as neglect
        return neglect

    last_strike_at = parse_dt(visit.get("last_strike_at"))
    if last_strike_at is not None and now - last_strike_at < TUNING.neglect_strike_min_interval:
        return neglect

    strikes = int(neglect.get("strikes", 0) or 0)
    neglect["strikes"] = strikes + 1
    visit["last_strike_at"] = iso_utc(now)
    neglect["visit"] = visit
    return neglect

