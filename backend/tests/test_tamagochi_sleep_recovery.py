"""Восстановление во сне: бодрость и HP с одинаковым sleep_recovery_mult."""

from datetime import datetime, timedelta, timezone

from app.games.tamagochi_world.constants import TUNING
from app.games.tamagochi_world.pet_state import (
    NeglectState,
    _hp_recovery_rate_sleeping,
    _sleep_recovery_rate,
    sync_pet_state,
)


def test_sleep_recovery_rates_doubled_by_mult() -> None:
    base_sleep = 100.0 / (float(TUNING.energy_recovery_hours_full) * 3600.0)
    assert _sleep_recovery_rate() == base_sleep * float(TUNING.sleep_recovery_mult)
    assert _hp_recovery_rate_sleeping() == float(TUNING.hp_up_per_sec_sleeping) * float(
        TUNING.sleep_recovery_mult
    )


def test_sleep_restores_sleepiness_and_hp_faster() -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    pet = {
        "alive": True,
        "is_sleeping": True,
        "stats": {"hp": 50, "hunger": 30, "sleepiness": 80, "mood": 50},
        "last_update_at": now.isoformat(),
        "activity": "wandering",
    }
    neglect: NeglectState = {}
    later = now + timedelta(hours=1)
    out = sync_pet_state(pet, neglect, now=later, offline=False)
    stats = out.pet["stats"]
    sleep_drop = 80 - int(stats["sleepiness"])
    hp_gain = int(stats["hp"]) - 50
    expected_sleep = int(_sleep_recovery_rate() * 3600)
    expected_hp = int(_hp_recovery_rate_sleeping() * 3600)
    assert sleep_drop == expected_sleep
    assert abs(hp_gain - expected_hp) <= 1
