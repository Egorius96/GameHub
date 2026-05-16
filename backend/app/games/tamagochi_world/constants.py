from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True, slots=True)
class TamagochiTuning:
    # World (square; ×4 от 5200×5200)
    world_w: float = 20800.0
    world_h: float = 20800.0
    pet_speed: float = 640.0  # px/sec — масштаб под размер поля

    # Offline simulation
    offline_rate: float = 0.25  # time goes slower offline

    # Critical thresholds
    hunger_crit: int = 90  # 0..100
    hp_crit: int = 20  # 0..100
    sleepiness_crit: int = 85  # 0..100

    # Per-second rates (online baseline)
    hunger_per_sec: float = 0.0035  # базовый рост голода бодрствуя
    mood_down_per_sec: float = 0.0020
    hp_down_per_sec_on_crit_hunger: float = 0.0040
    hp_down_per_sec_on_crit_sleep: float = 0.0015
    hp_up_per_sec_sleeping: float = 0.0030

    # Бодрость (UI: 100 - sleepiness): полный сон ~energy_recovery_hours_full ч;
    # sleep_recovery_mult ускоряет и бодрость, и hp_up_per_sec_sleeping во сне одинаково.
    energy_recovery_hours_full: float = 10.0
    sleep_recovery_mult: float = 2.0
    # Расход бодрости бодрствуя: границы 6–14 ч от активности и стресса (HP/голод/настроение)
    energy_drain_hours_min: float = 6.0
    energy_drain_hours_max: float = 14.0
    energy_drain_baseline_hours: float = 10.0  # «типичный» темп при wander + средние статы
    drain_stress_hp_weight: float = 0.38  # низкое HP → быстрее устаёт
    drain_stress_hunger_weight: float = 0.42  # сильный голод → быстрее устаёт
    drain_stress_mood_weight: float = 0.32  # низкое настроение → быстрее устаёт

    # Взаимное влияние на голод (реализм)
    hunger_hp_low_appetite: float = 0.22  # множитель голода при низком HP (меньше аппетит → медленнее растёт «голод»)
    hunger_mood_stress_eat: float = 0.14  # стресс/скука слегка ускоряют аппетит

    # Sleeping modifiers — во сне голод растёт медленнее, но не исчезает (как базальный метаболизм)
    hunger_sleep_mult: float = 0.52

    # Actions effects (deltas)
    # feed consumes 1 food item (shop) -> strong hunger reduction
    feed_hunger_delta: int = -45
    feed_mood_delta: int = 5
    feed_sleepiness_delta: int = -5

    owner_play_mood_delta: int = 25
    owner_play_hunger_delta: int = 5
    owner_play_sleepiness_delta: int = 10

    pet_pet_play_distance: float = 42.0
    pet_pet_play_duration: timedelta = timedelta(seconds=5)
    pet_pet_play_cooldown: timedelta = timedelta(seconds=25)
    pet_pet_play_mood_delta: int = 9
    # Встреча двух питомцев: 20% игра, 10% драка, 70% мимо
    pet_pet_encounter_play_chance: float = 0.20
    pet_pet_encounter_fight_chance: float = 0.10
    pet_pet_fight_duration_sec: float = 30.0
    pet_pet_fight_hp_damage_per_sec: float = 3.0
    pet_pet_fight_mood_per_sec: float = 1.2  # снижение настроения у обоих на время драки
    pet_pet_fight_hp_floor_pct: int = 15  # стоп драки; HP не уходит ниже для «смерти»
    # Бодрствующий рядом со спящим: шанс разбудить (игра/драка при этом запрещены)
    pet_wake_sleeping_chance: float = 0.05

    # Movement / player command
    arrival_distance_px: float = 12.0
    wander_resume_after_command: timedelta = timedelta(seconds=30)
    # Случайная цель блуждания не ближе этого отступа от края (px), чтобы не «тереться» о границу
    wander_margin_px: float = 1200.0

    # Map food pickups (wild food)
    map_food_pickup_radius: float = 48.0
    map_food_hunger_delta: int = -38
    map_food_mood_delta: int = 6
    map_food_ttl: timedelta = timedelta(minutes=2)
    map_food_max_active: int = 14
    # Интервалы спавна еды на карте (ещё ×2 реже к предыдущим значениям)
    map_food_initial_delay_sec: float = 80.0
    map_food_spawn_min_interval_sec: float = 360.0
    map_food_spawn_max_interval_sec: float = 1100.0

    # Wild diamonds: пауза между стартами поиска (base+rand)*factor; factor — из самочувствия и игрушки.
    # Ещё ×2 к 120/180 с → поиск стартует в среднем в 2 раза чаще.
    diamond_cooldown_min_sec: float = 60.0
    diamond_cooldown_rand_span_sec: float = 90.0
    diamond_search_duration_sec: float = 15.0

    # Карта: не показывать чужих питомцев, если хозяин не заходил в WS дольше этого (часы)
    map_offline_pet_visibility_hours: float = 24.0

    # Одновременно в tamagochi по WebSocket (поле мира)
    tamagochi_max_concurrent_players: int = 10

    # Neglect mechanics
    grace_window: timedelta = timedelta(minutes=2)
    neglect_strike_min_interval: timedelta = timedelta(hours=6)
    # Death: after 3 neglect strikes and >= 24 hours of accumulated critical-ignore time.
    neglect_strikes_required: int = 3
    neglect_dead_after: timedelta = timedelta(hours=24)


TUNING = TamagochiTuning()

# Множитель расхода «бодрости» (сонливости ↑) относительно базового темпа energy_drain_baseline_hours
ACTIVITY_ENERGY_DRAIN_MULT: dict[str, float] = {
    "wandering": 1.0,
    "moving": 1.12,
    "fighting": 1.52,
    "playing_with_other": 1.28,
    "eating_map_food": 0.88,
    "sleeping": 0.0,
    "digging": 1.22,
    "hunting": 1.22,
    "sparking": 1.22,
    "relaxing": 1.10,
    "scanning": 1.22,
    "exploring": 1.18,
    "__default__": 1.06,
}

