from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import hypot
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from app.core.config import settings
from app.core.gameshub import ensure_gameshub_schema
from app.core.session import sessions
from app.integrations.users_api import users_api

from .constants import TUNING
from .pet_history import diamond_age_cooldown_multiplier, estimate_best_diamond_interval_minutes, pet_age_days
from .pet_state import NeglectState, PetState, clamp_int, is_critical, register_visit, sync_pet_state
from .timeutils import iso_utc, parse_dt


PET_TYPES: Tuple[str, ...] = ("cat", "dog", "pokemon", "capybara", "alien")


@dataclass(slots=True)
class WorldPet:
    owner: str
    pet: PetState
    neglect: NeglectState
    last_persist_at: Optional[datetime] = None


PairKey = Tuple[str, str]


def _pair(a: str, b: str) -> PairKey:
    return (a, b) if a < b else (b, a)


class TamagochiWorld:
    """
    In-memory single-shard world.

    - Pets are loaded from users_api on demand and periodically refreshed.
    - When at least one client is online, the world ticks and pets move.
    """

    def __init__(self) -> None:
        self._pets: Dict[str, WorldPet] = {}
        self._connected: set[str] = set()
        self._last_refresh_at: Optional[datetime] = None
        self._last_tick_at: Optional[datetime] = None
        self._pair_cooldowns: Dict[PairKey, datetime] = {}
        self._events: list[dict] = []
        self._pickups: List[dict] = []
        self._next_map_food_spawn_at: Optional[datetime] = None
        # Последний раз хозяин был в tamagochi WS (connect или disconnect); для фильтра карты и prune.
        self._owner_last_online_at: Dict[str, datetime] = {}
        self._sim_lock = threading.RLock()

    def any_clients_connected(self) -> bool:
        return len(self._connected) > 0

    def run_simulation_step(self, *, now: datetime) -> None:
        """Один шаг refresh + tick под блокировкой — только из фонового цикла."""
        with self._sim_lock:
            self.refresh_from_users_api(now=now, max_age_seconds=15)
            self.tick(now=now)

    def snapshot_locked(self, *, now: datetime, me: str) -> dict:
        with self._sim_lock:
            return self.snapshot(now=now, me=me)

    def connect_owner(self, owner: str, pet: Optional[PetState], neglect: Optional[NeglectState], *, now: datetime) -> bool:
        with self._sim_lock:
            if owner not in self._connected and len(self._connected) >= int(TUNING.tamagochi_max_concurrent_players):
                return False
            self._connected.add(owner)
            self._owner_last_online_at[owner] = now
            if pet and pet.get("alive", True):
                self._pets[owner] = WorldPet(owner=owner, pet=pet, neglect=neglect or {}, last_persist_at=now)
                # entering view counts as visit for neglect logic (kept in persisted progress too)
                wp = self._pets[owner]
                wp.neglect = register_visit(wp.neglect, now=now, pet_is_critical=is_critical(wp.pet))
            return True

    def disconnect_owner(self, owner: str) -> None:
        with self._sim_lock:
            self._connected.discard(owner)
            now = datetime.now(timezone.utc)
            self._owner_last_online_at[owner] = now
            wp = self._pets.get(owner)
            if wp is not None:
                pet = wp.pet
                if pet.get("activity") == "fighting":
                    opp = pet.get("fight_with")
                    if isinstance(opp, str):
                        self._end_fight_pair(owner, opp, now=now, hp_floor_stop=False)
                self._interrupt_diamond_search(wp.pet, owner, now=now)

    def interrupt_diamond_search_if_active(self, pet: PetState, owner: str, *, now: datetime) -> None:
        """REST-действия и др.: сброс активного поиска алмаза."""
        with self._sim_lock:
            self._interrupt_diamond_search(pet, owner, now=now)

    def refresh_from_users_api(self, *, now: datetime, max_age_seconds: int = 15) -> None:
        if self._last_refresh_at is not None:
            if (now - self._last_refresh_at).total_seconds() < max_age_seconds:
                return

        catalog_user = settings.catalog_username
        catalog_pass = settings.catalog_password
        ok, users = users_api.fetch_project_users_list(catalog_user, catalog_pass)
        if not ok:
            return

        self._last_refresh_at = now

        if not isinstance(users, list):
            return

        valid_usernames: set[str] = set()

        for u in users:
            if not isinstance(u, dict):
                continue
            username = u.get("username")
            if not isinstance(username, str) or not username:
                continue
            valid_usernames.add(username)
            other = ensure_gameshub_schema(u.get("other_data") or {})
            games = other.get("games") or {}
            if not isinstance(games, dict):
                continue
            progress = games.get(settings.tamagochi_game_key) or {}
            if not isinstance(progress, dict):
                continue
            pet = progress.get("pet_state")
            if not isinstance(pet, dict) or not pet.get("alive", True):
                self._pets.pop(username, None)
                self._owner_last_online_at.pop(username, None)
                continue
            neglect = progress.get("neglect") or {}
            if not isinstance(neglect, dict):
                neglect = {}

            existing = self._pets.get(username)
            if existing is None:
                self._pets[username] = WorldPet(owner=username, pet=pet, neglect=neglect)
                la = parse_dt(progress.get("last_update_at"))
                self._owner_last_online_at[username] = la if la is not None else now
            else:
                if username in self._connected:
                    pass
                else:
                    # Не затираем pet из API: в памяти уже движение/tick, иначе скачки позиции.
                    existing.neglect = neglect

        # Пользователь удалён из БД — убираем питомца с карты и из симуляции.
        for owner in list(self._pets.keys()):
            if owner not in valid_usernames:
                self._pets.pop(owner, None)
                self._connected.discard(owner)
                self._owner_last_online_at.pop(owner, None)

    def remove_user_everywhere(self, username: str) -> None:
        """Немедленно убрать пользователя из мира (удаление аккаунта)."""
        with self._sim_lock:
            self._pets.pop(username, None)
            self._connected.discard(username)
            self._owner_last_online_at.pop(username, None)

    def tick(self, *, now: datetime) -> None:
        if self._last_tick_at is None:
            self._last_tick_at = now
            return
        if now <= self._last_tick_at:
            return

        dt_real = (now - self._last_tick_at).total_seconds()
        self._last_tick_at = now
        if dt_real <= 0:
            return
        # avoid big jumps per tick
        if dt_real > 0.5:
            dt_real = 0.5

        for oid in list(self._pets.keys()):
            if oid not in self._owner_last_online_at:
                self._owner_last_online_at[oid] = now

        # simulate pets
        for owner, wp in list(self._pets.items()):
            offline = owner not in self._connected
            res = sync_pet_state(wp.pet, wp.neglect, now=now, offline=offline)
            wp.pet = res.pet
            wp.neglect = res.neglect
            self._tick_activity(wp, now=now)
            if owner in self._connected:
                self._tick_ability_and_diamonds(wp, now=now)
            if not wp.pet.get("alive", True):
                # keep dead pet only for owner UI via REST; world hides dead pets
                if owner not in self._connected:
                    self._pets.pop(owner, None)
                    self._owner_last_online_at.pop(owner, None)

        self._tick_map_food_pickups(now=now)

        self._tick_pet_fights(now=now, dt_real=dt_real)

        # pet-pet: игра / драка / мимо
        owners = list(self._pets.keys())
        play_th = float(TUNING.pet_pet_encounter_play_chance)
        fight_th = play_th + float(TUNING.pet_pet_encounter_fight_chance)
        busy = frozenset({"fighting", "playing_with_other"})
        for i in range(len(owners)):
            for j in range(i + 1, len(owners)):
                a = owners[i]
                b = owners[j]
                pa = self._pets[a].pet
                pb = self._pets[b].pet
                posa = pa.get("pos") or {}
                posb = pb.get("pos") or {}
                ax = float(posa.get("x", 0.0))
                ay = float(posa.get("y", 0.0))
                bx = float(posb.get("x", 0.0))
                by = float(posb.get("y", 0.0))
                if hypot(ax - bx, ay - by) > TUNING.pet_pet_play_distance:
                    continue

                sleep_a = bool(pa.get("is_sleeping"))
                sleep_b = bool(pb.get("is_sleeping"))
                if sleep_a and sleep_b:
                    continue

                k = _pair(a, b)
                cd = self._pair_cooldowns.get(k)
                if cd is not None and now < cd:
                    continue

                if sleep_a or sleep_b:
                    self._pair_cooldowns[k] = now + TUNING.pet_pet_play_cooldown
                    h_wake = hashlib.sha256(
                        f"wake|{k[0]}|{k[1]}|{int(now.timestamp())}".encode("utf-8", errors="ignore")
                    ).digest()
                    r_wake = int.from_bytes(h_wake[:8], "big", signed=False) / float(2**64)
                    if r_wake < float(TUNING.pet_wake_sleeping_chance):
                        if sleep_a:
                            pa["is_sleeping"] = False
                            pa.pop("activity_until", None)
                            pa["activity"] = "moving" if pa.get("target") else "wandering"
                        if sleep_b:
                            pb["is_sleeping"] = False
                            pb.pop("activity_until", None)
                            pb["activity"] = "moving" if pb.get("target") else "wandering"
                        waker_o = b if sleep_a else a
                        sleeper_o = a if sleep_a else b
                        self._push_event(
                            {
                                "type": "pet_wake_by_other",
                                "waker": waker_o,
                                "sleeper": sleeper_o,
                                "at": iso_utc(now),
                            }
                        )
                    continue

                if pa.get("activity") in busy or pb.get("activity") in busy:
                    continue

                h = hashlib.sha256(f"{k[0]}|{k[1]}|{int(now.timestamp())}".encode("utf-8", errors="ignore")).digest()
                r = int.from_bytes(h[:8], "big", signed=False) / float(2**64)

                self._pair_cooldowns[k] = now + TUNING.pet_pet_play_cooldown

                if r < play_th:
                    sa = pa.get("stats") or {}
                    sb = pb.get("stats") or {}
                    sa["mood"] = min(100, int(sa.get("mood", 50)) + TUNING.pet_pet_play_mood_delta)
                    sb["mood"] = min(100, int(sb.get("mood", 50)) + TUNING.pet_pet_play_mood_delta)
                    pa["stats"] = sa
                    pb["stats"] = sb
                    pa["activity"] = "playing_with_other"
                    pb["activity"] = "playing_with_other"
                    until = iso_utc(now + TUNING.pet_pet_play_duration)
                    pa["activity_until"] = until
                    pb["activity_until"] = until
                    self._push_event({"type": "pet_play", "a": a, "b": b, "at": iso_utc(now)})
                elif r < fight_th:
                    fu = iso_utc(now + timedelta(seconds=float(TUNING.pet_pet_fight_duration_sec)))
                    pa["activity"] = "fighting"
                    pb["activity"] = "fighting"
                    pa["fight_with"] = b
                    pb["fight_with"] = a
                    pa["activity_until"] = fu
                    pb["activity_until"] = fu
                    self._push_event({"type": "pet_fight", "a": a, "b": b, "at": iso_utc(now)})
                # else: мимо — только кулдаун на пару

        self._prune_offline_pets_stale_on_map(now=now)

    def _owner_visible_on_public_map(self, owner: str, *, now: datetime) -> bool:
        if owner in self._connected:
            return True
        lo = self._owner_last_online_at.get(owner)
        if lo is None:
            return True
        return (now - lo) < timedelta(hours=float(TUNING.map_offline_pet_visibility_hours))

    def _prune_offline_pets_stale_on_map(self, *, now: datetime) -> None:
        max_age = timedelta(hours=float(TUNING.map_offline_pet_visibility_hours))
        for owner in list(self._pets.keys()):
            if owner in self._connected:
                continue
            lo = self._owner_last_online_at.get(owner)
            if lo is None:
                continue
            if now - lo >= max_age:
                self._pets.pop(owner, None)
                self._owner_last_online_at.pop(owner, None)

    def snapshot(self, *, now: datetime, me: str) -> dict:
        self._prune_events(now)
        pets_public = []
        for owner, wp in self._pets.items():
            pet = wp.pet
            if not pet.get("alive", True):
                continue
            if owner != me and not self._owner_visible_on_public_map(owner, now=now):
                continue
            stats = pet.get("stats") or {}
            public_stats = {"mood": int(stats.get("mood", 50))}
            pets_public.append(
                {
                    "owner": owner,
                    "pet_name": pet.get("pet_name"),
                    "type": pet.get("type"),
                    "pos": pet.get("pos"),
                    "is_sleeping": bool(pet.get("is_sleeping", False)),
                    "activity": pet.get("activity", "wandering"),
                    "activity_until": pet.get("activity_until"),
                    "stats": public_stats,
                    "online": owner in self._connected,
                }
            )
        pets_public.sort(key=lambda p: str(p.get("owner", "")).lower())

        me_pet = self._pets.get(me)
        pickups_public = []
        for pk in self._pickups:
            pickups_public.append(
                {
                    "id": pk.get("id"),
                    "for_type": pk.get("for_type"),
                    "pos": pk.get("pos"),
                    "expires_at": pk.get("expires_at"),
                }
            )

        diamond_info = None
        if me_pet is not None:
            diamond_info = TamagochiWorld._diamond_ui_info(me, me_pet.pet, now=now)

        return {
            "server_time": now.astimezone(timezone.utc).isoformat(),
            "world": {
                "w": TUNING.world_w,
                "h": TUNING.world_h,
                "diamond_search_duration_sec": float(TUNING.diamond_search_duration_sec),
                "pet_play_duration_sec": float(TUNING.pet_pet_play_duration.total_seconds()),
                "pet_fight_duration_sec": float(TUNING.pet_pet_fight_duration_sec),
                "pets": pets_public,
                "events": list(self._events),
                "pickups": pickups_public,
            },
            "me": {
                "pet": me_pet.pet if me_pet else None,
                "neglect": me_pet.neglect if me_pet else None,
                "diamond_info": diamond_info,
            },
        }

    def _push_event(self, ev: dict) -> None:
        # events are short-lived for UI animations
        self._events.append(ev)
        if len(self._events) > 50:
            self._events = self._events[-50:]

    def _prune_events(self, now: datetime) -> None:
        # keep last ~6 seconds
        cutoff = now.timestamp() - 6.0
        kept: list[dict] = []
        for ev in self._events:
            at = parse_dt(ev.get("at")) if isinstance(ev, dict) else None
            if at is None:
                kept.append(ev)
                continue
            if at.timestamp() >= cutoff:
                kept.append(ev)
        self._events = kept

    def _end_fight_pair(self, a: str, b: str | None, *, now: datetime, hp_floor_stop: bool) -> None:
        """Завершить драку у обоих; состояние «fighting» снимает только этот метод или disconnect."""
        for oid in (a, b):
            if not oid:
                continue
            wp = self._pets.get(oid)
            if wp is None:
                continue
            pet = wp.pet
            if pet.get("activity") != "fighting":
                continue
            pet.pop("fight_with", None)
            pet.pop("activity_until", None)
            if pet.get("target"):
                pet["activity"] = "moving"
            else:
                pet["activity"] = "wandering"
        if hp_floor_stop:
            self._push_event({"type": "pet_fight_end", "a": a, "b": b, "at": iso_utc(now), "reason": "hp_floor"})

    def _tick_pet_fights(self, *, now: datetime, dt_real: float) -> None:
        floor = int(TUNING.pet_pet_fight_hp_floor_pct)
        dmg_rate = float(TUNING.pet_pet_fight_hp_damage_per_sec)
        mood_rate = float(TUNING.pet_pet_fight_mood_per_sec)
        processed: set[PairKey] = set()
        for owner in list(self._pets.keys()):
            wp = self._pets.get(owner)
            if wp is None:
                continue
            pet = wp.pet
            if pet.get("activity") != "fighting":
                continue
            opp = pet.get("fight_with")
            if not isinstance(opp, str):
                pet.pop("fight_with", None)
                continue
            key = _pair(owner, opp)
            if key in processed:
                continue
            processed.add(key)
            owp = self._pets.get(opp)
            if owp is None:
                self._end_fight_pair(owner, opp, now=now, hp_floor_stop=False)
                continue
            pa, pb = pet, owp.pet
            if pb.get("fight_with") != owner:
                self._end_fight_pair(owner, opp, now=now, hp_floor_stop=False)
                continue

            until_a = parse_dt(pa.get("activity_until"))
            if until_a is not None and now >= until_a:
                self._end_fight_pair(owner, opp, now=now, hp_floor_stop=False)
                continue

            dmg = max(1, int(dmg_rate * dt_real))
            mood_loss = max(1, int(mood_rate * dt_real))
            sa = pa.get("stats") or {}
            sb = pb.get("stats") or {}
            ha = int(sa.get("hp", 100))
            hb = int(sb.get("hp", 100))
            ma = int(sa.get("mood", 50))
            mb = int(sb.get("mood", 50))
            ha_new = ha - dmg
            hb_new = hb - dmg
            ma_new = ma - mood_loss
            mb_new = mb - mood_loss
            stop_floor = ha_new < floor or hb_new < floor
            if stop_floor:
                ha_new = max(floor, ha_new)
                hb_new = max(floor, hb_new)
            sa["hp"] = clamp_int(ha_new)
            sb["hp"] = clamp_int(hb_new)
            sa["mood"] = clamp_int(ma_new)
            sb["mood"] = clamp_int(mb_new)
            pa["stats"] = sa
            pb["stats"] = sb
            if stop_floor:
                self._end_fight_pair(owner, opp, now=now, hp_floor_stop=True)

    def _tick_activity(self, wp: WorldPet, *, now: datetime) -> None:
        pet = wp.pet
        if pet.get("is_sleeping"):
            pet["activity"] = "sleeping"
            pet.pop("activity_until", None)
            return
        if pet.get("activity") == "fighting":
            return
        until = parse_dt(pet.get("activity_until"))
        if until is not None and now < until:
            return
        # derive from target
        if pet.get("target"):
            pet["activity"] = "moving"
        else:
            pet["activity"] = "wandering"
        pet.pop("activity_until", None)

    @staticmethod
    def _diamond_factor_before_rng(pet: PetState, *, now: datetime) -> tuple[float, bool, float]:
        """
        Множитель паузы между поисками (до случайной добавки), и блокировка.
        Третье значение — среднее самочувствие 0..100 по четырём шкалам (сытость = 100-голод).
        """
        stats = pet.get("stats") or {}
        hp = float(stats.get("hp", 100))
        hunger = float(stats.get("hunger", 0))
        sleepiness = float(stats.get("sleepiness", 0))
        mood = float(stats.get("mood", 50))
        fullness = 100.0 - hunger
        energy = 100.0 - sleepiness
        bars = [hp, fullness, energy, mood]
        avg_well = sum(max(0.0, min(100.0, v)) for v in bars) / 4.0
        # Раньше: любая шкала <35 — блок; при «голоде» 75 сытость 25 и поиск никогда не шёл.
        # Теперь: блок только если среднее самочувствие низкое.
        if avg_well < 38.0:
            return 0.0, True, avg_well

        score = avg_well
        t = (100.0 - score) / 65.0
        factor = 1.0 + 4.0 * max(0.0, min(1.0, t))

        buffs = pet.get("buffs") if isinstance(pet.get("buffs"), dict) else {}
        toy_diamond_until = parse_dt((buffs or {}).get("toy_diamond_until")) if isinstance(buffs, dict) else None
        if toy_diamond_until is not None and now < toy_diamond_until:
            factor *= 0.75

        return factor, False, avg_well

    @staticmethod
    def _diamond_cooldown_seconds(owner: str, pet: PetState, *, now: datetime) -> int:
        factor, blocked, _avg = TamagochiWorld._diamond_factor_before_rng(pet, now=now)
        if blocked:
            return 10**9

        b = int(now.timestamp() // 10)
        pid = str(pet.get("pet_id") or "")
        h = hashlib.sha256(f"{owner}|{pid}|{b}".encode("utf-8", errors="ignore")).digest()
        r = int.from_bytes(h[:2], "big", signed=False) / 65535.0
        base = float(TUNING.diamond_cooldown_min_sec)
        span = float(TUNING.diamond_cooldown_rand_span_sec)
        age_mult = diamond_age_cooldown_multiplier(pet, now=now)
        return int((base + r * span) * factor * age_mult)

    @staticmethod
    def _diamond_ui_info(owner: str, pet: PetState, *, now: datetime) -> dict:
        factor, blocked, avg_well = TamagochiWorld._diamond_factor_before_rng(pet, now=now)
        ab = pet.get("ability") if isinstance(pet.get("ability"), dict) else {}
        buffs = pet.get("buffs") if isinstance(pet.get("buffs"), dict) else {}

        toy_passive = parse_dt(buffs.get("toy_until")) if buffs else None
        toy_diamond = parse_dt(buffs.get("toy_diamond_until")) if buffs else None
        toy_boost = toy_diamond is not None and now < toy_diamond
        td_left_min: float | None = None
        if toy_boost and toy_diamond is not None:
            td_left_min = max(0.0, (toy_diamond - now).total_seconds() / 60.0)
        tp_left_h: float | None = None
        if toy_passive is not None and now < toy_passive:
            tp_left_h = max(0.0, (toy_passive - now).total_seconds() / 3600.0)

        pace = 0
        est_min = 0.0
        if not blocked and factor > 0:
            cd_med = (float(TUNING.diamond_cooldown_min_sec) + float(TUNING.diamond_cooldown_rand_span_sec) / 2.0) * factor
            age_mult = diamond_age_cooldown_multiplier(pet, now=now)
            cd_med *= age_mult
            est_min = cd_med / 60.0
            pace = int(round(100.0 - (factor - 1.0) / 4.0 * 80.0))
            pace = max(15, min(100, pace))

        age_days = round(pet_age_days(pet, now=now), 1)
        best_at_max = estimate_best_diamond_interval_minutes(pet, now=now, wellbeing_factor=factor if not blocked else 1.0)

        return {
            "blocked": blocked,
            "avg_wellbeing": round(avg_well, 1),
            "pace_percent": pace,
            "estimated_cooldown_minutes": round(est_min, 1) if not blocked else None,
            "pet_age_days": age_days,
            "best_diamond_interval_minutes": best_at_max if not blocked else None,
            "toy_diamond_boost": toy_boost,
            "toy_diamond_minutes_left": None if td_left_min is None else round(td_left_min, 1),
            "toy_passive_hours_left": None if tp_left_h is None else round(tp_left_h, 2),
            "next_diamond_at": ab.get("next_diamond_at"),
            "diamond_search_until": ab.get("diamond_search_until"),
        }

    def _interrupt_diamond_search(self, pet: PetState, owner: str, *, now: datetime) -> None:
        ab = pet.get("ability") if isinstance(pet.get("ability"), dict) else {}
        if not ab.get("diamond_search_until"):
            return
        ab2 = dict(ab)
        ab2.pop("diamond_search_until", None)
        cd = self._diamond_cooldown_seconds(owner, pet, now=now)
        ab2["next_diamond_at"] = iso_utc(now + timedelta(seconds=cd))
        pet["ability"] = ab2

    def _complete_diamond_search(self, wp: WorldPet, *, now: datetime, ability_name: str) -> None:
        pet = wp.pet
        owner = wp.owner
        cd = self._diamond_cooldown_seconds(owner, pet, now=now)
        ab = dict(pet.get("ability") or {})
        ab.pop("diamond_search_until", None)
        ab["next_diamond_at"] = iso_utc(now + timedelta(seconds=cd))
        pet["ability"] = ab

        new_total = users_api.increment_diamonds(owner, 1)
        if new_total is not None:
            for _t, sess in list(sessions.items()):
                if sess.username != owner:
                    continue
                o = ensure_gameshub_schema(sess.user.get("other_data") or {})
                o["diamonds"] = new_total
                sess.user["other_data"] = o

        pet["activity"] = ability_name
        pet["activity_until"] = iso_utc(now + TUNING.pet_pet_play_duration)
        self._push_event({"type": "diamond_found", "owner": owner, "at": iso_utc(now), "amount": 1, "pos": pet.get("pos"), "ability": ability_name})

    def _tick_ability_and_diamonds(self, wp: WorldPet, *, now: datetime) -> None:
        owner = wp.owner
        if owner not in self._connected:
            return

        pet = wp.pet
        if pet.get("is_sleeping"):
            self._interrupt_diamond_search(pet, owner, now=now)
            return
        if pet.get("activity") == "fighting":
            self._interrupt_diamond_search(pet, owner, now=now)
            return

        pet_type = str(pet.get("type") or "")
        ability_name = {
            "dog": "digging",
            "cat": "hunting",
            "pokemon": "sparking",
            "capybara": "relaxing",
            "alien": "scanning",
        }.get(pet_type, "exploring")

        ab_in = pet.get("ability") if isinstance(pet.get("ability"), dict) else {}
        search_until = parse_dt(ab_in.get("diamond_search_until"))

        if search_until is not None:
            if now >= search_until:
                self._complete_diamond_search(wp, now=now, ability_name=ability_name)
            return

        next_at = parse_dt(ab_in.get("next_diamond_at"))
        if next_at is None:
            pet.setdefault("ability", {})
            if not isinstance(pet.get("ability"), dict):
                pet["ability"] = {}
            pet["ability"]["next_diamond_at"] = iso_utc(now)
            next_at = now

        if now < next_at:
            return

        # если показатели низкие — поиск алмазов не запускаем (но периодически перепроверяем)
        cd_check = self._diamond_cooldown_seconds(owner, pet, now=now)
        if cd_check >= 10**8:
            pet.setdefault("ability", {})
            if not isinstance(pet.get("ability"), dict):
                pet["ability"] = {}
            pet["ability"]["next_diamond_at"] = iso_utc(now + timedelta(seconds=5))
            return

        dur = float(TUNING.diamond_search_duration_sec)
        ab = dict(ab_in)
        ab.pop("next_diamond_at", None)
        ab["diamond_search_until"] = iso_utc(now + timedelta(seconds=dur))
        pet["ability"] = ab

    def _tick_map_food_pickups(self, *, now: datetime) -> None:
        self._prune_expired_pickups(now)
        self._maybe_spawn_map_food(now)

        for pk in list(self._pickups):
            pid = str(pk.get("id") or "")
            if not pid:
                continue
            for_type = str(pk.get("for_type") or "")
            pos = pk.get("pos") or {}
            px = float(pos.get("x", 0.0))
            py = float(pos.get("y", 0.0))
            eaten = False
            for owner, wp in list(self._pets.items()):
                pet = wp.pet
                if not pet.get("alive", True) or pet.get("is_sleeping"):
                    continue
                if str(pet.get("type") or "") != for_type:
                    continue
                ppos = pet.get("pos") or {}
                cx = float(ppos.get("x", 0.0))
                cy = float(ppos.get("y", 0.0))
                if hypot(cx - px, cy - py) > float(TUNING.map_food_pickup_radius):
                    continue
                self._interrupt_diamond_search(pet, owner, now=now)
                stats = pet.get("stats") or {}
                stats["hunger"] = clamp_int(int(stats.get("hunger", 0)) + int(TUNING.map_food_hunger_delta))
                stats["mood"] = clamp_int(int(stats.get("mood", 50)) + int(TUNING.map_food_mood_delta))
                pet["stats"] = stats
                pet.setdefault("buffs", {})
                bf = pet.get("buffs") or {}
                if isinstance(bf, dict):
                    bf["well_fed_until"] = iso_utc(now + timedelta(hours=3))
                    pet["buffs"] = bf
                pet["activity"] = "eating_map_food"
                pet["activity_until"] = iso_utc(now + timedelta(seconds=4))
                eaten = True
                self._push_event(
                    {
                        "type": "map_food_eaten",
                        "owner": owner,
                        "for_type": for_type,
                        "at": iso_utc(now),
                        "pos": pk.get("pos"),
                    }
                )
                break
            if eaten:
                self._pickups = [p for p in self._pickups if str(p.get("id")) != pid]

    def _prune_expired_pickups(self, now: datetime) -> None:
        kept: List[dict] = []
        for pk in self._pickups:
            exp = parse_dt(pk.get("expires_at"))
            if exp is None or exp > now:
                kept.append(pk)
        self._pickups = kept

    def _maybe_spawn_map_food(self, now: datetime) -> None:
        if len(self._pickups) >= int(TUNING.map_food_max_active):
            return
        if self._next_map_food_spawn_at is None:
            self._next_map_food_spawn_at = now + timedelta(seconds=float(TUNING.map_food_initial_delay_sec))

        if now < self._next_map_food_spawn_at:
            return

        seed = int.from_bytes(hashlib.sha256(iso_utc(now).encode("utf-8")).digest()[:8], "big", signed=False)
        for_type = PET_TYPES[seed % len(PET_TYPES)]
        wx = max(60.0, min(TUNING.world_w - 60.0, float((seed >> 8) % int(TUNING.world_w - 120)) + 60.0))
        wy = max(60.0, min(TUNING.world_h - 60.0, float((seed >> 20) % int(TUNING.world_h - 120)) + 60.0))

        self._pickups.append(
            {
                "id": uuid4().hex,
                "for_type": for_type,
                "pos": {"x": wx, "y": wy},
                "expires_at": iso_utc(now + TUNING.map_food_ttl),
            }
        )

        span = float(TUNING.map_food_spawn_max_interval_sec - TUNING.map_food_spawn_min_interval_sec)
        frac = (seed % 10_000) / 10_000.0
        delay = float(TUNING.map_food_spawn_min_interval_sec) + frac * span
        self._next_map_food_spawn_at = now + timedelta(seconds=delay)


tamagochi_world = TamagochiWorld()

