"""Состояние мира: чанки, засыпание, реген алмазов, яблоки."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from app.games.minecraft_2d_online.constants import Mc2dParams, mc2d_params
from app.games.minecraft_2d_online.generator import generate_chunk_tiles, generate_surface_trees, surface_row_y, week_token
from app.games.minecraft_2d_online.tiles import Tile, is_refill_source, is_solid, normalize_tile


def _utc_today():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).date()


@dataclass
class ChunkWorld:
    p: Mc2dParams = field(default_factory=mc2d_params)
    world_seed: int = field(default_factory=lambda: random.randint(1, 2**31 - 1))
    iso_year: int = 0
    iso_week: int = 0
    week_id: int = 0
    chunks: dict[tuple[int, int], list[int]] = field(default_factory=dict)
    modified_chunks: set[tuple[int, int]] = field(default_factory=set)
    apples: set[tuple[int, int]] = field(default_factory=set)
    tree_by_x: dict[int, int] = field(default_factory=dict)
    tick_count: int = 0
    rng: random.Random = field(default_factory=random.Random)

    def __post_init__(self) -> None:
        if self.iso_year == 0:
            y, w = _utc_today().isocalendar()[:2]
            self.iso_year, self.iso_week = y, w
            self.week_id = week_token(y, w)
        self.rng = random.Random(self.world_seed ^ self.week_id)
        self._rebuild_trees()

    def _rebuild_trees(self) -> None:
        self.tree_by_x = generate_surface_trees(self.p, self.world_seed, self.week_id)

    def remove_tree_after_mine(self, gx: int, gy: int) -> bool:
        """Убрать дерево, если выкопан блок на поверхности или сразу под ней."""
        if gx not in self.tree_by_x:
            return False
        sy = self.surface_y()
        if gy not in (sy, sy + 1):
            return False
        del self.tree_by_x[gx]
        ay = max(0, sy - 1)
        for ax in (gx - 1, gx, gx + 1):
            self.apples.discard((ax, ay))
        return True

    def surface_y(self) -> int:
        return surface_row_y(self.p)

    def has_tree(self, gx: int) -> bool:
        return gx in self.tree_by_x

    def sync_week(self) -> bool:
        """True если неделя сменилась — нужен ресид."""
        y, w = _utc_today().isocalendar()[:2]
        new_wid = week_token(y, w)
        if new_wid != self.week_id:
            self.iso_year, self.iso_week = y, w
            self.week_id = new_wid
            self.chunks.clear()
            self.modified_chunks.clear()
            self.apples.clear()
            self.world_seed = self.rng.randint(1, 2**31 - 1)
            self.rng = random.Random(self.world_seed ^ self.week_id)
            self._rebuild_trees()
            return True
        return False

    def base_x(self) -> int:
        houses = self.trading_houses()
        if houses:
            return int(houses[0]["x"])
        if self.p.base_center_x is not None:
            return max(0, min(self.p.world_width_tiles - 1, self.p.base_center_x))
        return self.p.world_width_tiles // 2

    def trading_houses(self) -> list[dict[str, int]]:
        """Два торговых дома на карте (фиксированные доли ширины мира)."""
        p = self.p
        w = p.world_width_tiles
        sy = self.surface_y()
        margin = max(12, p.base_zone_radius + 4)
        return [
            {"x": margin, "y": sy, "v": 0},
            {"x": max(margin, w - margin - 1), "y": sy, "v": 1},
        ]

    def in_base_zone(self, gx: int, gy: int) -> bool:
        if gy > self.p.sky_rows + self.p.base_band_depth:
            return False
        r = self.p.base_zone_radius
        for h in self.trading_houses():
            if abs(gx - int(h["x"])) <= r:
                return True
        return False

    def chunk_coords(self, gx: int, gy: int) -> tuple[int, int]:
        cs = self.p.chunk_size
        return gx // cs, gy // cs

    def local_index(self, gx: int, gy: int) -> tuple[tuple[int, int], int]:
        cs = self.p.chunk_size
        cx, cy = gx // cs, gy // cs
        lx, ly = gx % cs, gy % cs
        return (cx, cy), ly * cs + lx

    def get_tile(self, gx: int, gy: int) -> int:
        if gx < 0 or gx >= self.p.world_width_tiles:
            return Tile.STONE
        if gy < 0 or gy >= self.p.sky_rows + self.p.world_depth_tiles:
            return Tile.AIR
        key, idx = self.local_index(gx, gy)
        ch = self.chunks.get(key)
        if ch is None:
            ch = generate_chunk_tiles(self.p, self.world_seed, self.week_id, key[0], key[1])
            self.chunks[key] = ch
        return normalize_tile(int(ch[idx]))

    def set_tile(self, gx: int, gy: int, t: int) -> None:
        if gx < 0 or gx >= self.p.world_width_tiles:
            return
        if gy < 0 or gy >= self.p.sky_rows + self.p.world_depth_tiles:
            return
        key, idx = self.local_index(gx, gy)
        ch = self.chunks.get(key)
        if ch is None:
            ch = generate_chunk_tiles(self.p, self.world_seed, self.week_id, key[0], key[1])
            self.chunks[key] = ch
        ch[idx] = normalize_tile(int(t))
        self.modified_chunks.add(key)

    def neighbors_4(self, gx: int, gy: int) -> list[tuple[int, int, int]]:
        out: list[tuple[int, int, int]] = []
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            x, y = gx + dx, gy + dy
            out.append((x, y, self.get_tile(x, y)))
        return out

    def tick_refill(self) -> list[tuple[int, int, int]]:
        """Возвращает список (gx, gy, new_tile) для клиента."""
        p = self.p
        changes: list[tuple[int, int, int]] = []
        cs = p.chunk_size
        # случайные пробы воздуха в изменённых чанках + редко глобально
        candidates: list[tuple[int, int]] = []
        for key in list(self.modified_chunks)[:40]:
            cx, cy = key
            for _ in range(8):
                lx = self.rng.randrange(cs)
                ly = self.rng.randrange(cs)
                gx, gy = cx * cs + lx, cy * cs + ly
                if self.get_tile(gx, gy) == Tile.AIR:
                    candidates.append((gx, gy))
        for _ in range(12):
            gx = self.rng.randrange(p.world_width_tiles)
            gy = self.rng.randrange(1, p.sky_rows + p.world_depth_tiles)
            if self.get_tile(gx, gy) == Tile.AIR:
                candidates.append((gx, gy))
        depth_scale = p.refill_depth_scale
        base_prob = p.refill_tick_prob_base
        for gx, gy in candidates:
            if self.get_tile(gx, gy) != Tile.AIR:
                continue
            depth = max(0, gy - p.sky_rows)
            prob = base_prob * (1.0 + depth * depth_scale)
            if self.rng.random() > prob:
                continue
            above = self.get_tile(gx, gy - 1)
            left = self.get_tile(gx - 1, gy)
            right = self.get_tile(gx + 1, gy)
            src = None
            if is_refill_source(above):
                src = above
            elif is_refill_source(left) and self.rng.random() < 0.5:
                src = left
            elif is_refill_source(right):
                src = right
            if src is None:
                continue
            self.set_tile(gx, gy, int(src))
            changes.append((gx, gy, int(src)))
        return changes

    def tick_diamonds(self) -> list[tuple[int, int]]:
        """Спавн кластеров алмазов; возвращает новые позиции."""
        p = self.p
        if self.tick_count % max(1, p.diamond_spawn_interval_ticks) != 0:
            return []
        placed: list[tuple[int, int]] = []
        min_gy = p.sky_rows + p.diamond_min_depth
        for _ in range(p.diamond_clusters_per_tick_max):
            gx = self.rng.randrange(p.world_width_tiles)
            gy = self.rng.randrange(min_gy, p.sky_rows + p.world_depth_tiles - 1)
            if self.get_tile(gx, gy) not in (Tile.STONE, Tile.DIRT, Tile.AIR):
                continue
            if self.get_tile(gx, gy) == Tile.AIR:
                if not any(is_solid(t) for _, _, t in self.neighbors_4(gx, gy)):
                    continue
            if self.rng.random() > 0.35:
                continue
            self.set_tile(gx, gy, Tile.DIAMOND)
            placed.append((gx, gy))
            if self.rng.random() < 0.4:
                dx, dy = self.rng.choice([(1, 0), (-1, 0), (0, 1)])
                g2x, g2y = gx + dx, gy + dy
                if 0 <= g2x < p.world_width_tiles and min_gy <= g2y < p.sky_rows + p.world_depth_tiles:
                    if self.get_tile(g2x, g2y) in (Tile.STONE, Tile.DIRT, Tile.AIR):
                        self.set_tile(g2x, g2y, Tile.DIAMOND)
                        placed.append((g2x, g2y))
        return placed

    def _pick_apple_spawn(self, tree_gx: int) -> tuple[int, int] | None:
        """Рядом с деревом: уровень неба (sy-1), в сторону от ствола."""
        p = self.p
        ay = max(0, self.surface_y() - 1)
        sides = [-1, 1]
        self.rng.shuffle(sides)
        for side in sides:
            ax = tree_gx + side
            if ax < 0 or ax >= p.world_width_tiles:
                continue
            if int(self.get_tile(ax, ay)) != Tile.AIR:
                continue
            if (ax, ay) in self.apples:
                continue
            return ax, ay
        return None

    def tick_apples(self) -> list[tuple[int, int]]:
        """Редкий спавн яблок у деревьев."""
        p = self.p
        added: list[tuple[int, int]] = []
        interval = max(1, p.apple_spawn_interval_ticks)
        if self.tick_count % interval != 0:
            return added
        if len(self.apples) >= p.apples_max:
            return added
        for _ in range(max(1, p.apple_spawn_attempts)):
            if len(self.apples) >= p.apples_max:
                break
            gx = self.rng.randrange(p.world_width_tiles)
            if not self.has_tree(gx):
                continue
            if self.rng.random() >= p.apple_spawn_chance:
                continue
            pos = self._pick_apple_spawn(gx)
            if pos is None:
                continue
            self.apples.add(pos)
            added.append(pos)
        return added

    def try_pick_apple(self, px: float, py: float) -> bool:
        p = self.p
        for ax, ay in list(self.apples):
            if (px - ax) ** 2 + (py - ay) ** 2 <= p.apple_pickup_radius**2:
                self.apples.discard((ax, ay))
                return True
        return False

    def snapshot_chunk_keys_near(self, gx: int, gy: int, radius_chunks: int = 2) -> dict[str, list]:
        cx, cy = self.chunk_coords(gx, gy)
        out: dict[str, list] = {}
        for dcx in range(-radius_chunks, radius_chunks + 1):
            for dcy in range(-radius_chunks, radius_chunks + 1):
                k = (cx + dcx, cy + dcy)
                ch = self.chunks.get(k)
                if ch is None:
                    ch = generate_chunk_tiles(self.p, self.world_seed, self.week_id, k[0], k[1])
                    self.chunks[k] = ch
                out[f"{k[0]},{k[1]}"] = list(ch)
        return out
