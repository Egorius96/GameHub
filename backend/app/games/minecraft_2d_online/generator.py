"""Процедурная генерация чанка (§13.6) + сид недели."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from app.games.minecraft_2d_online.tiles import Tile

if TYPE_CHECKING:
    from app.games.minecraft_2d_online.constants import Mc2dParams


def _mix64(seed: int) -> int:
    x = (seed + 0x9E3779B97F4A7C15) & ((1 << 64) - 1)
    z = x
    z ^= z >> 30
    z = (z * 0xBF58476D1CE4E5B9) & ((1 << 64) - 1)
    z ^= z >> 27
    z = (z * 0x94D049BB133111EB) & ((1 << 64) - 1)
    z ^= z >> 31
    return z


def chunk_rng(world_seed: int, week_id: int, cx: int, cy: int) -> random.Random:
    raw = _mix64(world_seed ^ (week_id * 0xC0FFEE) ^ (cx * 0x100000001B3) ^ (cy * 0xDEECE66D))
    return random.Random(raw)


def week_token(iso_year: int, iso_week: int) -> int:
    return iso_year * 100 + iso_week


def generate_chunk_tiles(
    p: "Mc2dParams",
    world_seed: int,
    week_id: int,
    cx: int,
    cy: int,
) -> list[int]:
    """
    Чанк размером chunk_size x chunk_size.
    Глобальные координаты: gx = cx*CS + lx, gy = cy*CS + ly (gy=0 sky, gy=1 поверхность).
    """
    cs = p.chunk_size
    rng = chunk_rng(world_seed, week_id, cx, cy)
    out: list[int] = [0] * (cs * cs)
    w = p.world_width_tiles
    for ly in range(cs):
        gy = cy * cs + ly
        if gy < 0 or gy >= p.sky_rows + p.world_depth_tiles:
            continue
        for lx in range(cs):
            gx = cx * cs + lx
            if gx < 0 or gx >= w:
                idx = ly * cs + lx
                out[idx] = Tile.STONE if gy >= p.sky_rows else Tile.AIR
                continue
            idx = ly * cs + lx
            out[idx] = _tile_at(p, rng, gx, gy)
    return out


def surface_row_y(p: "Mc2dParams") -> int:
    """Первая строка земли под небом (gy=0 — воздух)."""
    return p.sky_rows


def house_tree_blocked_gx(p: "Mc2dParams") -> set[int]:
    """Клетки X, где у торговых домов не ставим деревья."""
    w = p.world_width_tiles
    margin = max(12, p.base_zone_radius + 4)
    clear = p.base_zone_radius + 8
    blocked: set[int] = set()
    for hx in (margin, max(margin, w - margin - 1)):
        lo = max(0, hx - clear)
        hi = min(w - 1, hx + clear)
        for gx in range(lo, hi + 1):
            blocked.add(gx)
    return blocked


def generate_surface_trees(p: "Mc2dParams", world_seed: int, week_id: int) -> dict[int, int]:
    """Декоративные деревья на поверхности: gx -> variant 0..3 (детерминировано сидом)."""
    rng = random.Random(_mix64(world_seed ^ (week_id * 0xB1EE) ^ 0x7EEC))
    blocked = house_tree_blocked_gx(p)
    out: dict[int, int] = {}
    for gx in range(p.world_width_tiles):
        if gx in blocked:
            continue
        if rng.random() >= 0.18:
            continue
        tr = random.Random(_mix64(world_seed ^ week_id ^ (gx * 0x9E37)))
        out[gx] = tr.randrange(4)
    return out


def _tile_at(p: "Mc2dParams", rng: random.Random, gx: int, gy: int) -> int:
    if gy < surface_row_y(p):
        return Tile.AIR
    if gy == surface_row_y(p):
        return Tile.GRASS if rng.random() < 0.22 else Tile.SAND
    depth = gy - p.sky_rows
    if depth <= 4:
        return Tile.DIRT if rng.random() > 0.08 else Tile.SAND
    if depth <= 14:
        if rng.random() < 0.12 + depth * 0.008:
            return Tile.IRON
        return Tile.DIRT if rng.random() < 0.65 else Tile.STONE
    if depth <= 35:
        if rng.random() < 0.18 + depth * 0.004:
            return Tile.IRON
        if rng.random() < 0.002 + max(0, depth - 25) * 0.0004:
            return Tile.DIAMOND
        return Tile.STONE if rng.random() > 0.25 else Tile.DIRT
    # глубже
    if rng.random() < 0.28:
        return Tile.IRON
    if rng.random() < 0.004 + (depth - 35) * 0.00025:
        return Tile.DIAMOND
    return Tile.STONE
