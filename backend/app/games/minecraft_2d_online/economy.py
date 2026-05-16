"""Алмазная пыль, курс 8–20, переработка (§13.4–13.5)."""

from __future__ import annotations

import random

from app.games.minecraft_2d_online.constants import Mc2dParams


def roll_new_dust_rate(rng: random.Random, p: Mc2dParams) -> int:
    lo, hi = p.dust_rate_min, p.dust_rate_max
    if hi <= lo:
        return lo
    span = hi - lo
    # смесь: 70% — округлённое нормальное вокруг центра, 30% — равномерное
    if rng.random() < 0.72:
        mid = (lo + hi) / 2.0
        v = int(round(rng.gauss(mid, span / 5.0)))
    else:
        v = rng.randint(lo, hi)
    v = max(lo, min(hi, v))
    if hi - lo >= 2 and v in (lo, hi) and rng.random() > 0.12:
        v = rng.randint(lo + 1, hi - 1)
    return v


def dust_for_stone(rng: random.Random, p: Mc2dParams) -> int:
    return rng.randint(p.dust_stone_min, p.dust_stone_max)


def dust_for_iron(rng: random.Random, p: Mc2dParams) -> int:
    return rng.randint(p.dust_iron_min, p.dust_iron_max)
