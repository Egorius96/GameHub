"""Параметры MC2D из env (§13–14 GAME_RULES)."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

JUMP_HEIGHT_TILES = 1.5
STACK_MAX_BLOCKS = 64


@dataclass(frozen=True)
class Mc2dParams:
    chunk_size: int
    world_width_tiles: int
    world_depth_tiles: int
    sky_rows: int
    max_in_world: int
    dig_reach_tiles: float
    dig_reach_up_tiles: int
    dig_reach_down_tiles: int
    place_reach_up_tiles: int
    place_height_above_surface: int
    base_zone_radius: int
    dig_stamina_max: int
    dig_stamina_min_to_dig: int
    stamina_regen_surface: int
    stamina_regen_base: int
    stamina_regen_underground: float
    stamina_apple_pct: float
    apple_buy_dust_cost: int
    apple_spawn_interval_ticks: int
    apple_spawn_attempts: int
    apple_spawn_chance: float
    apples_max: int
    pickaxe_max_durability: int
    refill_tick_prob_base: float
    refill_depth_scale: float
    diamond_min_depth: int
    diamond_spawn_interval_ticks: int
    diamond_clusters_per_tick_max: int
    world_tick_ms: int
    base_band_depth: int
    base_center_x: int | None
    dust_stone_min: int
    dust_stone_max: int
    dust_iron_min: int
    dust_iron_max: int
    dust_rate_min: int
    dust_rate_max: int
    smelt_duration_sec: float
    apple_pickup_radius: float
    physics_substeps: int
    gravity_step: float
    jump_impulse: float
    escape_free_wait_sec: int
    escape_deep_rows: int
    physics_tick_ms: int
    walk_speed_tiles_per_sec: float


def _jump_impulse_for_height(
    gravity_step: float,
    physics_tick_ms: int,
    world_tick_ms: int,
    physics_substeps: int,
    height_tiles: float,
) -> float:
    """Начальная vy (вверх < 0) для прыжка примерно на height_tiles."""
    legacy_dt = max(1e-6, world_tick_ms / 1000.0)
    phys_dt = max(1e-6, physics_tick_ms / 1000.0)
    g_per_tick = gravity_step * (phys_dt / legacy_dt) * float(physics_substeps)
    g_per_sec = g_per_tick / phys_dt
    h = max(0.5, min(3.0, height_tiles))
    return -math.sqrt(2.0 * g_per_sec * h)


def mc2d_params() -> Mc2dParams:
    run_sec = float(os.getenv("MC2D_SURFACE_RUN_SEC", "30"))
    tiles_per_sec = float(os.getenv("MC2D_PLAYER_TILES_PER_SEC", "8"))
    width = int(os.getenv("MC2D_WORLD_WIDTH_TILES", str(int(run_sec * tiles_per_sec))))
    depth = int(os.getenv("MC2D_WORLD_DEPTH_TILES", "128"))
    cs = int(os.getenv("MC2D_CHUNK_SIZE", "32"))
    base_x_env = os.getenv("MC2D_BASE_CENTER_X", "").strip()
    base_cx: int | None = int(base_x_env) if base_x_env.isdigit() else None
    world_tick_ms = int(os.getenv("MC2D_WORLD_TICK_MS", "800"))
    physics_tick_ms = int(os.getenv("MC2D_PHYSICS_TICK_MS", "50"))
    physics_tick_ms = max(16, min(world_tick_ms, physics_tick_ms))
    return Mc2dParams(
        chunk_size=max(8, cs),
        world_width_tiles=max(32, width),
        world_depth_tiles=max(32, depth),
        sky_rows=1,
        max_in_world=int(os.getenv("MC2D_MAX_IN_WORLD", "10")),
        dig_reach_tiles=float(os.getenv("MC2D_DIG_REACH", "2")),
        dig_reach_up_tiles=int(os.getenv("MC2D_DIG_REACH_UP", "2")),
        dig_reach_down_tiles=int(os.getenv("MC2D_DIG_REACH_DOWN", "2")),
        place_reach_up_tiles=int(os.getenv("MC2D_PLACE_REACH_UP", "10")),
        place_height_above_surface=int(os.getenv("MC2D_PLACE_HEIGHT_ABOVE_SURFACE", "10")),
        base_zone_radius=int(os.getenv("MC2D_BASE_ZONE_RADIUS", "8")),
        dig_stamina_max=int(os.getenv("MC2D_DIG_STAMINA_MAX", "100")),
        dig_stamina_min_to_dig=int(os.getenv("MC2D_STAMINA_MIN_TO_DIG", "5")),
        stamina_regen_surface=int(os.getenv("MC2D_STAMINA_REGEN_SURFACE", "2")),
        stamina_regen_base=int(os.getenv("MC2D_STAMINA_REGEN_BASE", "4")),
        stamina_regen_underground=float(os.getenv("MC2D_STAMINA_REGEN_UNDERGROUND", "2")),
        stamina_apple_pct=float(os.getenv("MC2D_APPLE_STAMINA_PCT", "0.3")),
        apple_buy_dust_cost=int(os.getenv("MC2D_APPLE_BUY_DUST", "50")),
        apple_spawn_interval_ticks=int(os.getenv("MC2D_APPLE_SPAWN_INTERVAL", "60")),
        apple_spawn_attempts=int(os.getenv("MC2D_APPLE_SPAWN_ATTEMPTS", "1")),
        apple_spawn_chance=float(os.getenv("MC2D_APPLE_SPAWN_CHANCE", "0.08")),
        apples_max=int(os.getenv("MC2D_APPLES_MAX", "12")),
        pickaxe_max_durability=int(os.getenv("MC2D_PICKAXE_DURABILITY", "200")),
        refill_tick_prob_base=float(os.getenv("MC2D_REFILL_PROB_BASE", "0.012")),
        refill_depth_scale=float(os.getenv("MC2D_REFILL_DEPTH_SCALE", "0.02")),
        diamond_min_depth=int(os.getenv("MC2D_DIAMOND_MIN_DEPTH", "48")),
        diamond_spawn_interval_ticks=int(os.getenv("MC2D_DIAMOND_SPAWN_INTERVAL_TICKS", "45")),
        diamond_clusters_per_tick_max=int(os.getenv("MC2D_DIAMOND_CLUSTERS_PER_TICK", "2")),
        world_tick_ms=max(100, world_tick_ms),
        base_band_depth=int(os.getenv("MC2D_BASE_BAND_DEPTH", "6")),
        base_center_x=base_cx,
        dust_stone_min=int(os.getenv("MC2D_DUST_STONE_MIN", "1")),
        dust_stone_max=int(os.getenv("MC2D_DUST_STONE_MAX", "3")),
        dust_iron_min=int(os.getenv("MC2D_DUST_IRON_MIN", "3")),
        dust_iron_max=int(os.getenv("MC2D_DUST_IRON_MAX", "8")),
        dust_rate_min=int(os.getenv("MC2D_DUST_RATE_MIN", "8")),
        dust_rate_max=int(os.getenv("MC2D_DUST_RATE_MAX", "20")),
        smelt_duration_sec=float(os.getenv("MC2D_SMELT_SEC", "2.0")),
        apple_pickup_radius=float(os.getenv("MC2D_APPLE_RADIUS", "1.5")),
        physics_substeps=max(8, int(os.getenv("MC2D_PHYSICS_SUBSTEPS", "28"))),
        gravity_step=float(os.getenv("MC2D_GRAVITY_STEP", "0.016")),
        jump_impulse=_jump_impulse_for_height(
            float(os.getenv("MC2D_GRAVITY_STEP", "0.016")),
            physics_tick_ms,
            world_tick_ms,
            max(8, int(os.getenv("MC2D_PHYSICS_SUBSTEPS", "28"))),
            float(os.getenv("MC2D_JUMP_HEIGHT", str(JUMP_HEIGHT_TILES))),
        ),
        escape_free_wait_sec=int(os.getenv("MC2D_ESCAPE_FREE_SEC", "10")),
        escape_deep_rows=int(os.getenv("MC2D_ESCAPE_DEEP_ROWS", "12")),
        physics_tick_ms=physics_tick_ms,
        walk_speed_tiles_per_sec=float(os.getenv("MC2D_WALK_SPEED", "4.25")),
    )
