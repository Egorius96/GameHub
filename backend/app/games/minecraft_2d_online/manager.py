"""Лобби, мир до 10 игроков, WS, тики засыпания и экономика."""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from app.core.config import settings
from app.games.minecraft_2d_online.constants import mc2d_params
from app.games.minecraft_2d_online.economy import dust_for_iron, dust_for_stone, roll_new_dust_rate
from app.games.minecraft_2d_online.tiles import (
    PLACEABLE_ITEMS,
    Tile,
    blocks_movement,
    inv_stack_cap,
    mineable,
    tile_mine_drop,
)
from app.games.minecraft_2d_online.world import ChunkWorld
from app.integrations.users_api import _sync_session_diamonds, users_api

# Хитбокс игрока (тайлы): py — верх, низ на py + PLAYER_H; ширина меньше клетки.
PLAYER_W = 0.72
PLAYER_H = 1.0
_MAX_VSTEP = 0.28
JUMP_HEIGHT_TILES = 1.5


def _now() -> float:
    return time.monotonic()


@dataclass
class Mc2dPlayer:
    username: str
    in_world: bool
    px: float
    py: float
    stamina: int
    pickaxe: int
    inv: dict[str, int]
    dust: int
    dust_rate: int
    dust_history: list[int]
    ws: WebSocket | None = None
    connected: bool = True
    playtime_join_mon: float = field(default_factory=_now)
    vy: float = 0.0
    jump_requested: bool = False
    jump_origin_py: float | None = None
    escape_free_until_ts: float | None = None
    input_dx: int = 0
    face_left: bool = False
    stamina_regen_acc: float = 0.0

    def inv_add(self, k: str, n: int = 1) -> None:
        cur = int(self.inv.get(k, 0))
        cap = inv_stack_cap(k)
        if cap is not None:
            self.inv[k] = min(cap, cur + n)
        else:
            self.inv[k] = cur + n


@dataclass
class Minecraft2DManager:
    world: ChunkWorld = field(default_factory=ChunkWorld)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    players: dict[str, Mc2dPlayer] = field(default_factory=dict)
    world_usernames: list[str] = field(default_factory=list)
    queue_usernames: list[str] = field(default_factory=list)
    connections: dict[str, WebSocket] = field(default_factory=dict)

    def _game_key(self) -> str:
        return settings.minecraft_2d_online_game_key

    def _load_user_progress(self, username: str) -> tuple[int, int, list[int]]:
        db = users_api._db()
        try:
            from app.core.gameshub import ensure_gameshub_schema
            from app.db.models import GameHubUser

            u = db.query(GameHubUser).filter(GameHubUser.username == username).first()
            if u is None:
                return 0, 14, []
            other = ensure_gameshub_schema(u.other_data or {})
            g = (other.get("games") or {}).get(self._game_key()) or {}
            if not isinstance(g, dict):
                return 0, 14, []
            dust = int(g.get("diamond_dust", 0))
            rate = int(g.get("dust_exchange_rate", 14) or 14)
            hist = g.get("dust_rate_history") or []
            hist2 = [int(x) for x in hist[-8:]] if isinstance(hist, list) else []
            return dust, max(8, min(20, rate)), hist2
        finally:
            db.close()

    def _persist_dust_state(
        self,
        username: str,
        *,
        dust: int | None = None,
        rate: int | None = None,
        append_history: int | None = None,
    ) -> None:
        gk = self._game_key()

        def mut(g: dict) -> None:
            if dust is not None:
                g["diamond_dust"] = max(0, int(dust))
            if rate is not None:
                g["dust_exchange_rate"] = max(8, min(20, int(rate)))
            if append_history is not None:
                h = g.get("dust_rate_history")
                if not isinstance(h, list):
                    h = []
                h = list(h) + [int(append_history)]
                g["dust_rate_history"] = h[-16:]

        users_api.patch_game_data(username, gk, mut)

    def _load_world_state(self, username: str) -> dict[str, Any] | None:
        db = users_api._db()
        try:
            from app.core.gameshub import ensure_gameshub_schema
            from app.db.models import GameHubUser

            u = db.query(GameHubUser).filter(GameHubUser.username == username).first()
            if u is None:
                return None
            other = ensure_gameshub_schema(u.other_data or {})
            g = (other.get("games") or {}).get(self._game_key()) or {}
            if not isinstance(g, dict):
                return None
            ws = g.get("world_state")
            if not isinstance(ws, dict):
                return None
            if int(ws.get("week_id", -1)) != int(self.world.week_id):
                return None
            return ws
        finally:
            db.close()

    def _persist_world_state(self, pl: Mc2dPlayer) -> None:
        inv = {k: int(v) for k, v in pl.inv.items() if int(v) > 0}

        def mut(g: dict) -> None:
            g["world_state"] = {
                "week_id": int(self.world.week_id),
                "x": round(float(pl.px), 4),
                "y": round(float(pl.py), 4),
                "inv": inv,
                "stamina": int(pl.stamina),
                "pickaxe": int(pl.pickaxe),
            }

        users_api.patch_game_data(pl.username, self._game_key(), mut)

    def _apply_world_state(self, pl: Mc2dPlayer, ws: dict[str, Any]) -> bool:
        p = self.world.p
        try:
            px = float(ws["x"])
            py = float(ws["y"])
        except (KeyError, TypeError, ValueError):
            return False
        max_row = self._max_row()
        pl.px = max(0.0, min(float(p.world_width_tiles) - PLAYER_W - 1e-3, px))
        pl.py = max(0.0, min(float(max_row) - PLAYER_H + 0.02, py))
        inv = ws.get("inv")
        if isinstance(inv, dict):
            pl.inv = {str(k): int(v) for k, v in inv.items() if int(v) > 0}
        pl.stamina = max(0, min(p.dig_stamina_max, int(ws.get("stamina", pl.stamina))))
        pl.pickaxe = max(0, min(p.pickaxe_max_durability, int(ws.get("pickaxe", pl.pickaxe))))
        pl.vy = 0.0
        pl.input_dx = 0
        pl.jump_origin_py = None
        self._unstuck_player(pl)
        return True

    def _restore_player_position(self, pl: Mc2dPlayer) -> bool:
        saved = self._load_world_state(pl.username)
        if saved and self._apply_world_state(pl, saved):
            return True
        sx, sy = self._spawn_xy()
        pl.px, pl.py = sx, sy
        pl.vy = 0.0
        pl.input_dx = 0
        pl.jump_origin_py = None
        return False

    def _maybe_roll_rate(self, pl: Mc2dPlayer) -> None:
        p = self.world.p
        if self.world.tick_count % 120 == 0 and self.world.rng.random() < 0.35:
            new_r = roll_new_dust_rate(self.world.rng, p)
            pl.dust_rate = new_r
            self._persist_dust_state(pl.username, rate=new_r, append_history=new_r)

    def _spawn_xy(self) -> tuple[float, float]:
        p = self.world.p
        for _ in range(80):
            px = float(self.world.rng.randrange(max(1, p.world_width_tiles - 2)))
            py = 0.0
            if self.world.get_tile(int(px), 0) != Tile.AIR:
                continue
            below = self.world.get_tile(int(px), 1)
            if blocks_movement(below):
                return px, py
        return float(p.world_width_tiles // 2), 0.0

    def _player_cell(self, pl: Mc2dPlayer) -> tuple[int, int]:
        p = self.world.p
        ix = int(math.floor(pl.px + 1e-9))
        iy = int(math.floor(pl.py + 1e-9))
        return max(0, min(p.world_width_tiles - 1, ix)), max(0, min(p.sky_rows + p.world_depth_tiles - 1, iy))

    def _max_row(self) -> int:
        p = self.world.p
        return p.sky_rows + p.world_depth_tiles - 1

    def _player_aabb(self, pl: Mc2dPlayer, *, px: float | None = None, py: float | None = None) -> tuple[float, float, float, float]:
        hx = pl.px if px is None else px
        hy = pl.py if py is None else py
        x0 = hx + (1.0 - PLAYER_W) * 0.5
        return x0, hy, x0 + PLAYER_W, hy + PLAYER_H

    def _tile_blocked(self, tx: int, ty: int) -> bool:
        p = self.world.p
        if tx < 0 or tx >= p.world_width_tiles or ty > self._max_row():
            return True
        if ty < 0:
            return False
        return blocks_movement(int(self.world.get_tile(tx, ty)))

    def _aabb_blocked(self, x0: float, y0: float, x1: float, y1: float) -> bool:
        tx0 = int(math.floor(x0 + 1e-9))
        tx1 = int(math.floor(x1 - 1e-9))
        ty0 = max(0, int(math.floor(y0 + 1e-9)))
        ty1 = int(math.floor(y1 - 1e-9))
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                if self._tile_blocked(tx, ty):
                    return True
        return False

    def _tx_span(self, x0: float, x1: float) -> range:
        p = self.world.p
        a = max(0, int(math.floor(x0 + 1e-9)))
        b = min(p.world_width_tiles - 1, int(math.floor(x1 - 1e-9)))
        return range(a, b + 1) if a <= b else range(0)

    def _center_in_solid(self, pl: Mc2dPlayer) -> bool:
        cx = pl.px + 0.5
        cy = pl.py + PLAYER_H * 0.5
        tx = int(math.floor(cx + 1e-9))
        ty = int(math.floor(cy + 1e-9))
        if ty < 0:
            return False
        return self._tile_blocked(tx, ty)

    def _resolve_inside_solids(self, pl: Mc2dPlayer, *, max_push: float = 0.45) -> None:
        """Выталкивает только если центр внутри блока (не стены ямы)."""
        pushed = 0.0
        for _ in range(24):
            if not self._center_in_solid(pl):
                return
            pl.py -= 0.04
            pl.vy = min(0.0, pl.vy)
            pushed += 0.04
            if pushed >= max_push:
                return
        min_py = self._min_py_allowed()
        if pl.py < min_py:
            pl.py = min_py
            if pl.vy < 0.0:
                pl.vy = 0.0

    def _snap_to_ground(self, pl: Mc2dPlayer) -> None:
        """Опора только под ногами, без притягивания к поверхности мира."""
        if pl.vy < -0.02 or not self._grounded(pl):
            return
        x0, _, x1, y1 = self._player_aabb(pl)
        feet = y1
        snap_py: float | None = None
        max_row = self._max_row()
        foot_cell = int(math.floor(feet + 1e-4))
        for tx in self._tx_span(x0, x1):
            for ty in range(max(0, foot_cell - 1), min(max_row, foot_cell + 2) + 1):
                if not self._tile_blocked(tx, ty):
                    continue
                if feet <= float(ty) + 1e-3:
                    continue
                stand_py = float(ty) - PLAYER_H
                if snap_py is None or stand_py > snap_py:
                    snap_py = stand_py
        if snap_py is not None and pl.py > snap_py - 1e-4:
            pl.py = snap_py
            pl.vy = min(0.0, pl.vy)

    def _clamp_jump_height(self, pl: Mc2dPlayer) -> None:
        if pl.jump_origin_py is None:
            return
        cap_py = pl.jump_origin_py - JUMP_HEIGHT_TILES
        if pl.py < cap_py:
            pl.py = cap_py
            if pl.vy < 0.0:
                pl.vy = 0.0

    def _resolve_ceiling(self, pl: Mc2dPlayer) -> None:
        if pl.vy >= -1e-6:
            return
        x0, y0, x1, _ = self._player_aabb(pl)
        head_ty = int(math.floor(y0 + 1e-9))
        if head_ty < 0:
            return
        for tx in self._tx_span(x0, x1):
            if self._tile_blocked(tx, head_ty):
                pl.py = float(head_ty + 1) + 0.02
                pl.vy = 0.0
                return

    def _grounded(self, pl: Mc2dPlayer) -> bool:
        """Ноги на верхней грани твёрдого блока (поверхность и пол ямы)."""
        x0, _, x1, y1 = self._player_aabb(pl)
        feet = y1
        max_row = self._max_row()
        for tx in self._tx_span(x0, x1):
            support = int(math.floor(feet + 1e-4))
            if support < 0:
                continue
            if support > max_row:
                return True
            if not self._tile_blocked(tx, support):
                continue
            if abs(feet - float(support)) <= 0.14:
                return True
        return False

    def _aabb_overlaps_blocks(self, pl: Mc2dPlayer, *, px: float | None = None, py: float | None = None) -> bool:
        x0, y0, x1, y1 = self._player_aabb(pl, px=px, py=py)
        return self._aabb_blocked(x0, y0, x1, y1)

    def _unstuck_player(self, pl: Mc2dPlayer) -> None:
        """Сдвиг из пересечения с блоками после копания / застревания в яме."""
        if not self._aabb_overlaps_blocks(pl):
            return
        ox, oy = pl.px, pl.py
        best: tuple[float, float, float] | None = None
        for dy in (0.0, -0.12, 0.12, -0.24, 0.24, -0.4, 0.4):
            for dx in (0.0, -0.15, 0.15, -0.3, 0.3):
                npx, npy = ox + dx, oy + dy
                if not self._aabb_overlaps_blocks(pl, px=npx, py=npy):
                    score = abs(dx) + abs(dy)
                    if best is None or score < best[0]:
                        best = (score, npx, npy)
        if best is not None:
            pl.px, pl.py = best[1], best[2]
            pl.vy = min(0.0, pl.vy)

    def _min_py_allowed(self) -> float:
        """Верх мира: достаточно неба для прыжка на JUMP_HEIGHT_TILES."""
        p = self.world.p
        headroom = max(0.0, float(p.sky_rows) - 1.0) + JUMP_HEIGHT_TILES + 0.08
        return -headroom

    def _collide_vertical(self, pl: Mc2dPlayer) -> None:
        p = self.world.p
        max_row = self._max_row()
        min_py = self._min_py_allowed()
        if pl.py < min_py:
            pl.py = min_py
            if pl.vy < 0.0:
                pl.vy = 0.0
        max_top = float(max_row) - PLAYER_H + 0.02
        if pl.py > max_top:
            pl.py, pl.vy = max_top, min(0.0, pl.vy)
        self._resolve_inside_solids(pl)
        self._resolve_ceiling(pl)
        self._snap_to_ground(pl)
        self._resolve_inside_solids(pl)
        min_py = self._min_py_allowed()
        if pl.py < min_py:
            pl.py = min_py
            if pl.vy < 0.0:
                pl.vy = 0.0

    def _physics_player(self, pl: Mc2dPlayer, dt: float) -> None:
        if not pl.in_world:
            return
        p = self.world.p
        legacy_dt = max(1e-6, p.world_tick_ms / 1000.0)
        g_scale = dt / legacy_dt
        if pl.jump_requested:
            if self._grounded(pl):
                pl.vy = p.jump_impulse
                pl.jump_origin_py = pl.py
            pl.jump_requested = False
        sub = max(4, p.physics_substeps)
        g = p.gravity_step * g_scale
        for _ in range(sub):
            pl.vy += g
            dy = pl.vy
            while abs(dy) > 1e-9:
                step = max(-_MAX_VSTEP, min(_MAX_VSTEP, dy))
                pl.py += step
                dy -= step
                self._clamp_jump_height(pl)
                self._collide_vertical(pl)
        self._apply_horizontal(pl, dt)
        self._resolve_inside_solids(pl)
        self._snap_to_ground(pl)
        self._clamp_jump_height(pl)
        self._unstuck_player(pl)
        if self._grounded(pl):
            pl.jump_origin_py = None
        elif pl.jump_origin_py is not None and pl.py > pl.jump_origin_py - JUMP_HEIGHT_TILES + 0.05:
            pl.jump_origin_py = None
        if self.world.try_pick_apple(pl.px, pl.py):
            pl.inv_add("apple", 1)
        self._stamina_regen_physics(pl, dt)

    def _can_move_to(self, pl: Mc2dPlayer, npx: float, npy: float) -> bool:
        x0, y0, x1, y1 = self._player_aabb(pl, px=npx, py=npy)
        if y0 < self._min_py_allowed() or y1 > float(self._max_row()) + 1.0:
            return False
        return not self._aabb_blocked(x0, y0, x1, y1)

    def _apply_horizontal(self, pl: Mc2dPlayer, dt: float) -> None:
        p = self.world.p
        dx_total = float(pl.input_dx) * p.walk_speed_tiles_per_sec * max(0.0, dt)
        if abs(dx_total) < 1e-9:
            return
        steps = max(1, int(math.ceil(abs(dx_total) / 0.04)))
        inc = dx_total / float(steps)
        for _ in range(steps):
            nx = pl.px + inc
            moved = False
            for ny in (pl.py, pl.py - 0.12, pl.py + 0.12):
                if self._can_move_to(pl, nx, ny):
                    pl.px, pl.py = nx, ny
                    moved = True
                    break
            if not moved:
                break

    def _tile_reach_ok(
        self,
        pl: Mc2dPlayer,
        tx: int,
        ty: int,
        *,
        reach_up: int,
        reach_down: int,
    ) -> bool:
        p = self.world.p
        pcx = pl.px + 0.5
        tcx = float(tx) + 0.5
        if abs(tcx - pcx) > p.dig_reach_tiles + 1e-6:
            return False
        head_cell = int(math.floor(pl.py + 1e-9))
        feet_cell = int(math.floor(pl.py + PLAYER_H - 1e-9))
        if ty < head_cell and head_cell - ty > reach_up:
            return False
        if ty > feet_cell and ty - feet_cell > reach_down:
            return False
        x0, y0, x1, y1 = self._player_aabb(pl)
        if x0 < float(tx) + 1.0 and x1 > float(tx) and y0 < float(ty) + 1.0 and y1 > float(ty):
            return False
        return True

    def _can_reach_tile(self, pl: Mc2dPlayer, tx: int, ty: int) -> bool:
        p = self.world.p
        return self._tile_reach_ok(
            pl, tx, ty, reach_up=p.dig_reach_up_tiles, reach_down=p.dig_reach_down_tiles
        )

    def _can_place_tile(self, pl: Mc2dPlayer, tx: int, ty: int) -> bool:
        p = self.world.p
        sy = self.world.surface_y()
        if ty < sy or ty > sy + p.place_height_above_surface:
            return False
        return self._tile_reach_ok(
            pl, tx, ty, reach_up=p.place_reach_up_tiles, reach_down=p.dig_reach_down_tiles
        )

    def _mine_adjacent(self, pl: Mc2dPlayer, tx: int, ty: int) -> bool:
        return self._can_reach_tile(pl, tx, ty)

    def _teleport_surface(self, pl: Mc2dPlayer) -> None:
        sx, sy = self._spawn_xy()
        pl.px, pl.py = sx, sy
        pl.vy = 0.0
        pl.input_dx = 0
        pl.jump_origin_py = None

    def _teleport_base(self, pl: Mc2dPlayer) -> None:
        """Телепорт к ближайшему торговому дому на поверхности."""
        houses = self.world.trading_houses()
        if houses:
            hx = int(min(houses, key=lambda h: abs(int(h["x"]) - pl.px))["x"])
        else:
            hx = self.world.base_x()
        pl.px = float(hx)
        pl.py = 0.0
        pl.vy = 0.0
        pl.input_dx = 0
        pl.jump_origin_py = None
        self._unstuck_player(pl)
        self._persist_world_state(pl)

    def _escape_available(self, pl: Mc2dPlayer) -> bool:
        p = self.world.p
        if not pl.in_world:
            return False
        _, iy = self._player_cell(pl)
        return pl.stamina < p.dig_stamina_min_to_dig and iy >= p.sky_rows + p.escape_deep_rows

    def _stamina_regen(self, pl: Mc2dPlayer, dt: float = 0.0) -> None:
        p = self.world.p
        ix, iy = self._player_cell(pl)
        if self.world.in_base_zone(ix, iy):
            pl.stamina = min(p.dig_stamina_max, pl.stamina + p.stamina_regen_base)
        elif iy <= p.sky_rows + 3:
            pl.stamina = min(p.dig_stamina_max, pl.stamina + p.stamina_regen_surface)
        elif dt > 0 and p.stamina_regen_underground > 0:
            pl.stamina_regen_acc += p.stamina_regen_underground * dt
            while pl.stamina_regen_acc >= 1.0:
                pl.stamina_regen_acc -= 1.0
                pl.stamina = min(p.dig_stamina_max, pl.stamina + 1)

    def _stamina_regen_physics(self, pl: Mc2dPlayer, dt: float) -> None:
        """Под землёй — плавная медленная регенерация каждый кадр физики."""
        p = self.world.p
        ix, iy = self._player_cell(pl)
        if self.world.in_base_zone(ix, iy) or iy <= p.sky_rows + 3:
            return
        self._stamina_regen(pl, dt)

    def _dig_cost(self, tile: int) -> int:
        return {Tile.SAND: 3, Tile.DIRT: 5, Tile.STONE: 12, Tile.IRON: 18, Tile.DIAMOND: 28, Tile.GRASS: 2}.get(
            int(tile), 8
        )

    def _apple_stamina_gain(self) -> int:
        p = self.world.p
        pct = max(0.0, min(1.0, float(p.stamina_apple_pct)))
        return max(1, int(math.ceil(p.dig_stamina_max * pct)))

    def _try_join_world(self, username: str) -> dict[str, Any]:
        p = self.world.p
        pl = self.players.get(username)
        if not pl:
            return {"ok": False, "error": "no_player"}
        if pl.in_world:
            return {"ok": True, "in_world": True, "queue_pos": None}
        if len(self.world_usernames) < p.max_in_world:
            pl.in_world = True
            self._restore_player_position(pl)
            pl.escape_free_until_ts = None
            pl.playtime_join_mon = _now()
            if username not in self.world_usernames:
                self.world_usernames.append(username)
            if username in self.queue_usernames:
                self.queue_usernames.remove(username)
            return {"ok": True, "in_world": True, "queue_pos": None}
        if username not in self.queue_usernames:
            self.queue_usernames.append(username)
        pos = self.queue_usernames.index(username) + 1
        return {"ok": True, "in_world": False, "queue_pos": pos}

    def _leave_world(self, username: str) -> None:
        pl = self.players.get(username)
        if not pl:
            return
        pl.input_dx = 0
        if pl.in_world:
            pl.in_world = False
            if username in self.world_usernames:
                self.world_usernames.remove(username)
            self._persist_world_state(pl)
            self._persist_playtime(username, pl)
        if username in self.queue_usernames:
            self.queue_usernames.remove(username)
        self._promote_queue()

    def _promote_queue(self) -> None:
        p = self.world.p
        while len(self.world_usernames) < p.max_in_world and self.queue_usernames:
            nxt = self.queue_usernames.pop(0)
            pl2 = self.players.get(nxt)
            if pl2 and pl2.connected:
                pl2.in_world = True
                self._restore_player_position(pl2)
                pl2.escape_free_until_ts = None
                pl2.playtime_join_mon = _now()
                self.world_usernames.append(nxt)

    def _persist_playtime(self, username: str, pl: Mc2dPlayer) -> None:
        dt = int(max(0, _now() - pl.playtime_join_mon))
        if dt <= 0:
            return
        pl.playtime_join_mon = _now()
        gk = self._game_key()

        def mut(g: dict) -> None:
            g["playtime"] = int(g.get("playtime", 0)) + dt

        users_api.patch_game_data(username, gk, mut)

    def _physics_meta(self) -> dict[str, float]:
        p = self.world.p
        legacy_dt = max(1e-6, p.world_tick_ms / 1000.0)
        phys_dt = max(1e-6, p.physics_tick_ms / 1000.0)
        vy_per_tick = p.gravity_step * (phys_dt / legacy_dt) * float(p.physics_substeps)
        return {
            "tick_ms": float(p.physics_tick_ms),
            "vy_per_tick": vy_per_tick,
            "jump_impulse": float(p.jump_impulse),
        }

    def snapshot_public(self, for_username: str | None = None) -> dict[str, Any]:
        p = self.world.p
        players_out = []
        for un in self.world_usernames:
            pl = self.players.get(un)
            if pl and pl.in_world:
                players_out.append(
                    {
                        "username": un,
                        "x": pl.px,
                        "y": pl.py,
                        "vy": pl.vy,
                        "stamina": pl.stamina,
                        "face_left": bool(pl.face_left),
                    }
                )
        apples = [{"x": ax, "y": ay} for ax, ay in self.world.apples]
        sy = self.world.surface_y()
        trees = [{"x": gx, "y": sy, "v": v} for gx, v in self.world.tree_by_x.items()]
        out: dict[str, Any] = {
            "type": "snapshot",
            "week_id": self.world.week_id,
            "world_seed": self.world.world_seed,
            "width": p.world_width_tiles,
            "depth": p.world_depth_tiles,
            "sky_rows": p.sky_rows,
            "chunk_size": p.chunk_size,
            "max_in_world": p.max_in_world,
            "in_world_count": len(self.world_usernames),
            "queue": list(self.queue_usernames),
            "players": players_out,
            "apples": apples,
            "trees": trees,
            "base_x": self.world.base_x(),
            "houses": self.world.trading_houses(),
            "base_zone_radius": p.base_zone_radius,
            "physics": self._physics_meta(),
        }
        if for_username:
            pl = self.players.get(for_username)
            if pl:
                gh = users_api.get_diamond_balance(for_username)
                out["self"] = {
                    "in_world": pl.in_world,
                    "queue_pos": (self.queue_usernames.index(for_username) + 1)
                    if for_username in self.queue_usernames
                    else None,
                    "x": pl.px,
                    "y": pl.py,
                    "vy": pl.vy,
                    "stamina": pl.stamina,
                    "stamina_max": p.dig_stamina_max,
                    "pickaxe": pl.pickaxe,
                    "inv": dict(pl.inv),
                    "dust": pl.dust,
                    "dust_rate": pl.dust_rate,
                    "dust_history": list(pl.dust_history),
                    "diamonds_gamehub": int(gh or 0),
                    "escape": {
                        "available": self._escape_available(pl),
                        "free_ends_at": pl.escape_free_until_ts,
                    },
                    "face_left": bool(pl.face_left),
                    "apple_stamina_gain": self._apple_stamina_gain(),
                    "apple_buy_dust_cost": p.apple_buy_dust_cost,
                }
        return out

    async def register_ws(self, username: str, ws: WebSocket) -> dict[str, Any]:
        async with self.lock:
            dust, rate, hist = self._load_user_progress(username)
            pp = mc2d_params()
            pl = self.players.get(username)
            if pl is None:
                saved = self._load_world_state(username)
                px = float(pp.world_width_tiles // 2)
                py = 0.0
                inv: dict[str, int] = {}
                stamina = pp.dig_stamina_max
                pickaxe = pp.pickaxe_max_durability
                if saved:
                    try:
                        px = float(saved["x"])
                        py = float(saved["y"])
                    except (KeyError, TypeError, ValueError):
                        pass
                    s_inv = saved.get("inv")
                    if isinstance(s_inv, dict):
                        inv = {str(k): int(v) for k, v in s_inv.items() if int(v) > 0}
                    stamina = max(0, min(pp.dig_stamina_max, int(saved.get("stamina", stamina))))
                    pickaxe = max(0, min(pp.pickaxe_max_durability, int(saved.get("pickaxe", pickaxe))))
                pl = Mc2dPlayer(
                    username=username,
                    in_world=False,
                    px=px,
                    py=py,
                    stamina=stamina,
                    pickaxe=pickaxe,
                    inv=inv,
                    dust=dust,
                    dust_rate=rate,
                    dust_history=hist,
                    connected=True,
                )
                self.players[username] = pl
                self._unstuck_player(pl)
            else:
                pl.dust, pl.dust_rate, pl.dust_history = dust, rate, hist
                pl.connected = True
            pl.ws = ws
            self.connections[username] = ws
            self._try_join_world(username)
            return self.snapshot_public(for_username=username)

    async def snapshot_for(self, username: str | None) -> dict[str, Any]:
        async with self.lock:
            return self.snapshot_public(for_username=username)

    async def unregister_ws(self, username: str) -> None:
        async with self.lock:
            pl = self.players.get(username)
            if pl:
                pl.connected = False
                pl.ws = None
                self._leave_world(username)
            self.connections.pop(username, None)

    async def handle_message(self, username: str, data: dict[str, Any]) -> dict[str, Any] | None:
        async with self.lock:
            t = str(data.get("type") or "")
            pl = self.players.get(username)
            if not pl:
                return {"error": "no_player"}
            if t == "join_world":
                return self._try_join_world(username)
            if t == "leave_world":
                self._leave_world(username)
                return {"ok": True}
            if t == "move":
                if not pl.in_world:
                    return {"error": "not_in_world"}
                dx = int(data.get("dx") or 0)
                dx = max(-1, min(1, dx))
                if pl.escape_free_until_ts is not None and dx != 0:
                    pl.escape_free_until_ts = None
                pl.input_dx = dx
                if dx < 0:
                    pl.face_left = True
                elif dx > 0:
                    pl.face_left = False
                return None
            if t == "jump":
                if not pl.in_world:
                    return {"error": "not_in_world"}
                if pl.escape_free_until_ts is not None:
                    pl.escape_free_until_ts = None
                pl.jump_requested = True
                return None
            if t == "use_apple":
                if not pl.in_world:
                    return {"error": "not_in_world"}
                if int(pl.inv.get("apple", 0)) <= 0:
                    return {"error": "no_apple"}
                pl.inv["apple"] = int(pl.inv["apple"]) - 1
                gain = self._apple_stamina_gain()
                pl.stamina = min(self.world.p.dig_stamina_max, pl.stamina + gain)
                return {"ok": True, "stamina": pl.stamina, "stamina_gain": gain}
            if t == "buy_apple":
                if not pl.in_world or not self.world.in_base_zone(int(pl.px), int(pl.py)):
                    return {"error": "not_at_base"}
                p = self.world.p
                cost = p.apple_buy_dust_cost
                if pl.dust < cost:
                    return {"error": "no_dust"}
                cap = inv_stack_cap("apple") or 64
                if int(pl.inv.get("apple", 0)) >= cap:
                    return {"error": "stack_full"}
                pl.dust -= cost
                pl.inv_add("apple", 1)
                self._persist_dust_state(pl.username, dust=pl.dust)
                return {
                    "ok": True,
                    "dust": pl.dust,
                    "apples": int(pl.inv.get("apple", 0)),
                    "dust_spent": cost,
                }
            if t == "mine":
                if not pl.in_world:
                    return {"error": "not_in_world"}
                if pl.escape_free_until_ts is not None:
                    pl.escape_free_until_ts = None
                tx = int(data.get("tx"))
                ty = int(data.get("ty"))
                if not self._mine_adjacent(pl, tx, ty):
                    return {"error": "too_far"}
                tile = self.world.get_tile(tx, ty)
                if not mineable(tile):
                    return {"error": "not_mineable"}
                p = self.world.p
                if pl.stamina < p.dig_stamina_min_to_dig:
                    return {"error": "no_stamina"}
                cost = self._dig_cost(tile)
                if pl.stamina < cost:
                    return {"error": "no_stamina"}
                if pl.pickaxe <= 0 and int(tile) in (Tile.STONE, Tile.IRON, Tile.DIAMOND):
                    return {"error": "pickaxe_broken"}
                pl.stamina -= cost
                if int(tile) in (Tile.STONE, Tile.IRON, Tile.DIAMOND):
                    pl.pickaxe = max(0, pl.pickaxe - 1)
                self.world.set_tile(tx, ty, Tile.AIR)
                self._unstuck_player(pl)
                tree_removed = self.world.remove_tree_after_mine(tx, ty)
                it = int(tile)
                drop = tile_mine_drop(it)
                if drop:
                    pl.inv_add(drop, 1)
                self._stamina_regen(pl)
                out_mine: dict[str, Any] = {
                    "ok": True,
                    "tile": it,
                    "tx": tx,
                    "ty": ty,
                    "set_tile": int(Tile.AIR),
                }
                if tree_removed:
                    out_mine["tree_removed_x"] = tx
                return out_mine
            if t == "place":
                if not pl.in_world:
                    return {"error": "not_in_world"}
                if pl.escape_free_until_ts is not None:
                    pl.escape_free_until_ts = None
                tx = int(data.get("tx"))
                ty = int(data.get("ty"))
                item = str(data.get("item") or "")
                if item not in PLACEABLE_ITEMS:
                    return {"error": "invalid_block"}
                if not self._can_place_tile(pl, tx, ty):
                    return {"error": "too_far"}
                if self.world.get_tile(tx, ty) != Tile.AIR:
                    return {"error": "not_air"}
                if int(pl.inv.get(item, 0)) < 1:
                    return {"error": "no_block"}
                pl.inv[item] = int(pl.inv[item]) - 1
                new_t = int(PLACEABLE_ITEMS[item])
                self.world.set_tile(tx, ty, new_t)
                return {"ok": True, "tx": tx, "ty": ty, "set_tile": new_t}
            if t == "smelt":
                if not pl.in_world or not self.world.in_base_zone(int(pl.px), int(pl.py)):
                    return {"error": "not_at_base"}
                stone_n = int(pl.inv.get("stone_block", 0))
                iron_n = int(pl.inv.get("iron_block", 0))
                if stone_n + iron_n <= 0:
                    return {"error": "no_ore"}
                rng = self.world.rng
                wp = self.world.p
                dust_gain = 0
                for _ in range(stone_n):
                    dust_gain += dust_for_stone(rng, wp)
                for _ in range(iron_n):
                    dust_gain += dust_for_iron(rng, wp)
                if stone_n:
                    pl.inv["stone_block"] = 0
                if iron_n:
                    pl.inv["iron_block"] = 0
                pl.dust += dust_gain
                self._persist_dust_state(pl.username, dust=pl.dust)
                return {
                    "ok": True,
                    "dust_gain": dust_gain,
                    "dust": pl.dust,
                    "smelted_stone": stone_n,
                    "smelted_iron": iron_n,
                }
            if t == "exchange_diamond_for_dust":
                if not pl.in_world or not self.world.in_base_zone(int(pl.px), int(pl.py)):
                    return {"error": "not_at_base"}
                idem = str(data.get("idempotency_key") or "").strip()[:128]
                out = users_api.mc2d_exchange_diamond_for_dust(username, idem)
                if not out.get("ok"):
                    return {"error": out.get("error", "exchange_failed")}
                pl.dust = int(out.get("dust", pl.dust))
                pl.dust_rate = int(out.get("rate", pl.dust_rate))
                return {
                    "ok": True,
                    "dust": pl.dust,
                    "gained": int(out.get("gained", 0)),
                    "rate": pl.dust_rate,
                    "diamonds": int(out.get("diamonds", 0)),
                    "cached": bool(out.get("cached")),
                }
            if t == "deliver_raw_diamond":
                idem = str(data.get("idempotency_key") or "").strip()[:128]
                if not idem:
                    return {"error": "idempotency_required"}
                if not pl.in_world or not self.world.in_base_zone(int(pl.px), int(pl.py)):
                    return {"error": "not_at_base"}
                if int(pl.inv.get("raw_diamond", 0)) < 1:
                    return {"error": "no_raw"}
                gk = self._game_key()
                from app.core.gameshub import ensure_gameshub_schema
                from app.db.models import GameHubUser

                db = users_api._db()
                try:
                    u = db.query(GameHubUser).filter(GameHubUser.username == username).with_for_update().first()
                    if u is None:
                        return {"error": "user"}
                    other = ensure_gameshub_schema(u.other_data or {})
                    games = other.setdefault("games", {})
                    if not isinstance(games, dict):
                        games = {}
                        other["games"] = games
                    g = games.get(gk)
                    if not isinstance(g, dict):
                        g = {}
                    de = g.get("deliver_idempotency")
                    if not isinstance(de, dict):
                        de = {}
                    if idem in de:
                        db.commit()
                        return {"ok": True, "cached": True, "diamonds": int(other.get("diamonds", 0))}
                    cur = int(other.get("diamonds", 0))
                    pl.inv["raw_diamond"] = int(pl.inv.get("raw_diamond", 0)) - 1
                    try:
                        other["diamonds"] = cur + 1
                        de[idem] = {"at": int(time.time())}
                        kk = list(de.keys())[-80:]
                        g["deliver_idempotency"] = {k: de[k] for k in kk}
                        games[gk] = g
                        u.other_data = other
                        db.commit()
                    except Exception:
                        pl.inv["raw_diamond"] = int(pl.inv.get("raw_diamond", 0)) + 1
                        db.rollback()
                        return {"error": "server"}
                    _sync_session_diamonds(username, int(other["diamonds"]))
                    return {"ok": True, "cached": False, "diamonds": int(other["diamonds"])}
                except Exception:
                    db.rollback()
                    return {"error": "server"}
                finally:
                    db.close()
            if t in ("teleport_base_paid", "escape_surface_paid"):
                if not pl.in_world:
                    return {"error": "not_in_world"}
                pl.escape_free_until_ts = None
                bal = users_api.get_diamond_balance(username)
                if bal is None or bal < 1:
                    return {"error": "no_diamond"}
                nb = users_api.adjust_diamonds(username, -1)
                if nb is None:
                    return {"error": "no_diamond"}
                self._teleport_base(pl)
                return {"ok": True, "diamonds": nb, "teleport": "base"}
            if t == "escape_surface_free":
                if not pl.in_world:
                    return {"error": "not_in_world"}
                if pl.escape_free_until_ts is not None:
                    return {"error": "escape_already_pending"}
                p = self.world.p
                pl.escape_free_until_ts = time.time() + float(p.escape_free_wait_sec)
                return {"ok": True, "escape_ends_at": pl.escape_free_until_ts, "escape": "free_wait"}
            return {"error": "unknown_type"}

    async def broadcast(self) -> None:
        async with self.lock:
            con = dict(self.connections)
            for un, ws in con.items():
                try:
                    snap = self.snapshot_public(for_username=un)
                    await ws.send_json(snap)
                except Exception:
                    continue

    async def tick_physics_frame(self, dt: float) -> None:
        async with self.lock:
            now_ts = time.time()
            for pl in self.players.values():
                if pl.in_world and pl.escape_free_until_ts is not None and now_ts >= pl.escape_free_until_ts:
                    pl.inv.clear()
                    pl.escape_free_until_ts = None
                    self._teleport_surface(pl)
            for pl in self.players.values():
                if pl.in_world:
                    self._physics_player(pl, dt)

    async def tick_world_slow(self) -> None:
        patch_msg: dict[str, Any] | None = None
        async with self.lock:
            reset = self.world.sync_week()
            if reset:
                for un in list(self.world_usernames):
                    pl = self.players.get(un)
                    if pl:
                        pl.in_world = False
                    if un not in self.queue_usernames:
                        self.queue_usernames.append(un)
                self.world_usernames.clear()
                self._promote_queue()
            self.world.tick_count += 1
            for pl in self.players.values():
                if pl.in_world:
                    self._maybe_roll_rate(pl)
                    self._stamina_regen(pl)
            changes = self.world.tick_refill()
            dnew = self.world.tick_diamonds()
            self.world.tick_apples()
            patch_msg = {
                "type": "patches",
                "refill": [{"x": x, "y": y, "t": t} for x, y, t in changes],
                "diamonds": [{"x": x, "y": y} for x, y in dnew],
                "week_reset": reset,
            }
        if patch_msg:
            for un, ws in list(self.connections.items()):
                try:
                    await ws.send_json(patch_msg)
                except Exception:
                    pass


minecraft_2d_manager = Minecraft2DManager()

_mc2d_task: asyncio.Task[None] | None = None


async def minecraft_2d_background_loop() -> None:
    slow_acc = 0.0
    while True:
        p = mc2d_params()
        phys_ms = float(p.physics_tick_ms)
        dt = max(0.016, phys_ms / 1000.0)
        await asyncio.sleep(dt)
        try:
            await minecraft_2d_manager.tick_physics_frame(dt)
            await minecraft_2d_manager.broadcast()
            slow_acc += phys_ms
            while slow_acc >= float(p.world_tick_ms):
                slow_acc -= float(p.world_tick_ms)
                await minecraft_2d_manager.tick_world_slow()
        except Exception:
            pass


def start_minecraft_2d_background_loop() -> None:
    global _mc2d_task
    if _mc2d_task is not None and not _mc2d_task.done():
        return
    _mc2d_task = asyncio.create_task(minecraft_2d_background_loop(), name="mc2d_tick")


async def stop_minecraft_2d_background_loop() -> None:
    global _mc2d_task
    if _mc2d_task is None or _mc2d_task.done():
        _mc2d_task = None
        return
    _mc2d_task.cancel()
    try:
        await _mc2d_task
    except asyncio.CancelledError:
        pass
    _mc2d_task = None
