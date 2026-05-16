from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal


ItemType = Literal["food", "toy"]


@dataclass(frozen=True, slots=True)
class ShopPrices:
    food_diamonds: int
    toy_diamonds: int
    # coins are internal currency used to buy; exchange rate is also variable
    diamonds_to_coins_rate: int  # coins per 1 diamond


def _bucket_hour(now: datetime) -> int:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return int(now.astimezone(timezone.utc).timestamp() // 3600)


def _rand01(key: str) -> float:
    h = hashlib.sha256(key.encode("utf-8", errors="ignore")).digest()
    n = int.from_bytes(h[:8], "big", signed=False)
    return (n % 10_000_000) / 10_000_000.0


def get_shop_prices(now: datetime) -> ShopPrices:
    """
    Deterministic floating prices by hour.

    Economy targets:
    - 1 food ~= 2 diamonds on average; enough for ~5-10h if used at critical.
    - toys are more expensive and improve mood efficiency / slow decay.
    """
    b = _bucket_hour(now)

    # multipliers 0.8..1.3
    m_food = 0.8 + 0.5 * _rand01(f"food|{b}")
    m_toy = 0.85 + 0.65 * _rand01(f"toy|{b}")
    m_rate = 0.9 + 0.4 * _rand01(f"rate|{b}")

    base_food = 2
    base_toy = 6
    base_rate = 10  # 1 diamond -> 10 coins baseline

    food = max(1, int(round(base_food * m_food)))
    toy = max(2, int(round(base_toy * m_toy)))
    rate = max(6, int(round(base_rate * m_rate)))
    return ShopPrices(food_diamonds=food, toy_diamonds=toy, diamonds_to_coins_rate=rate)


def item_effects_doc() -> dict:
    """
    Returned to UI to show dependencies/description in shop menu.
    """
    return {
        "food": {
            "desc": "Еда: расходуется при кормлении. Сильно снижает голод и даёт бонус сытости на несколько часов.",
            "effects": {
                "hunger_delta": -45,
                "well_fed_hours": "5-10 (зависит от питомца/настроения, в среднем ~7)",
            },
        },
        "toy": {
            "desc": "Игрушка: пассивно улучшает настроение. Также даёт краткий буст к поиску алмазов (10 минут).",
            "effects": {
                "mood_decay_mult": 0.85,
                "owner_play_mood_bonus": +10,
                "duration_hours": 24,
                "diamond_boost_minutes": 10,
            },
        },
        "coins": {
            "desc": "Внутренняя валюта Tamagochi World. Можно обменять из алмазов (общая валюта всех игр).",
        },
    }

