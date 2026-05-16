"""Тесты Minecraft 2D Online: генерация, курс пыли, тайлы."""

import random

import pytest

from app.games.minecraft_2d_online.constants import Mc2dParams
from app.games.minecraft_2d_online.economy import dust_for_iron, dust_for_stone, roll_new_dust_rate
from app.games.minecraft_2d_online.generator import generate_chunk_tiles
from app.games.minecraft_2d_online.tiles import Tile, blocks_movement, mineable


@pytest.fixture
def p() -> Mc2dParams:
    return Mc2dParams(
        chunk_size=16,
        world_width_tiles=64,
        world_depth_tiles=64,
        sky_rows=1,
        max_in_world=10,
        dig_reach_tiles=2.0,
        dig_reach_up_tiles=2,
        dig_reach_down_tiles=2,
        place_reach_up_tiles=10,
        place_height_above_surface=10,
        base_zone_radius=8,
        dig_stamina_max=100,
        dig_stamina_min_to_dig=5,
        stamina_regen_surface=2,
        stamina_regen_base=4,
        stamina_regen_underground=2.0,
        stamina_apple_pct=0.3,
        apple_buy_dust_cost=50,
        apple_spawn_interval_ticks=60,
        apple_spawn_attempts=1,
        apple_spawn_chance=0.08,
        apples_max=12,
        pickaxe_max_durability=200,
        refill_tick_prob_base=0.01,
        refill_depth_scale=0.02,
        diamond_min_depth=20,
        diamond_spawn_interval_ticks=10,
        diamond_clusters_per_tick_max=1,
        world_tick_ms=500,
        base_band_depth=6,
        base_center_x=None,
        dust_stone_min=1,
        dust_stone_max=3,
        dust_iron_min=3,
        dust_iron_max=8,
        dust_rate_min=8,
        dust_rate_max=20,
        smelt_duration_sec=2.0,
        apple_pickup_radius=1.5,
        physics_substeps=16,
        gravity_step=0.02,
        jump_impulse=-0.5,
        escape_free_wait_sec=10,
        escape_deep_rows=12,
        physics_tick_ms=50,
        walk_speed_tiles_per_sec=4.25,
    )


def test_roll_new_dust_rate_in_range(p: Mc2dParams) -> None:
    rng = random.Random(42)
    for _ in range(200):
        v = roll_new_dust_rate(rng, p)
        assert 8 <= v <= 20


def test_dust_for_stone_iron_bounds(p: Mc2dParams) -> None:
    rng = random.Random(1)
    for _ in range(50):
        assert 1 <= dust_for_stone(rng, p) <= 3
        assert 3 <= dust_for_iron(rng, p) <= 8


def test_generate_chunk_tiles_valid_enums(p: Mc2dParams) -> None:
    tiles = generate_chunk_tiles(p, world_seed=12345, week_id=202601, cx=0, cy=0)
    assert len(tiles) == p.chunk_size * p.chunk_size
    for t in tiles:
        assert t in list(Tile)


def test_tree_not_mineable() -> None:
    assert not mineable(int(Tile.TREE))


def test_grass_blocks_movement_tree_tile_does_not() -> None:
    from app.games.minecraft_2d_online.tiles import normalize_tile

    assert blocks_movement(int(Tile.GRASS))
    assert not blocks_movement(int(Tile.TREE))
    assert normalize_tile(int(Tile.TREE)) == int(Tile.SAND)


def test_surface_chunks_have_no_tree_tiles(p: Mc2dParams) -> None:
    from app.games.minecraft_2d_online.generator import generate_chunk_tiles
    from app.games.minecraft_2d_online.tiles import Tile

    tiles = generate_chunk_tiles(p, world_seed=99, week_id=202601, cx=0, cy=0)
    assert int(Tile.TREE) not in tiles


def test_surface_trees_four_variants(p: Mc2dParams) -> None:
    from app.games.minecraft_2d_online.generator import generate_surface_trees

    trees = generate_surface_trees(p, world_seed=42, week_id=202601)
    assert trees
    assert all(0 <= v <= 3 for v in trees.values())


def test_no_trees_at_house_positions(p: Mc2dParams) -> None:
    from app.games.minecraft_2d_online.generator import house_tree_blocked_gx
    from app.games.minecraft_2d_online.world import ChunkWorld

    w = ChunkWorld()
    w.p = p
    blocked = house_tree_blocked_gx(p)
    for hx in (int(h["x"]) for h in w.trading_houses()):
        assert hx in blocked
        assert hx not in w.tree_by_x


def test_tree_removed_when_mining_surface_or_under(p: Mc2dParams) -> None:
    from app.games.minecraft_2d_online.world import ChunkWorld

    w = ChunkWorld()
    w.p = p
    gx = min(p.world_width_tiles // 2, 30)
    w.tree_by_x[gx] = 1
    sy = w.surface_y()
    assert w.remove_tree_after_mine(gx, sy + 1)
    assert gx not in w.tree_by_x
    w.tree_by_x[gx] = 2
    assert w.remove_tree_after_mine(gx, sy)
    assert gx not in w.tree_by_x
    w.tree_by_x[gx] = 0
    assert not w.remove_tree_after_mine(gx, sy + 5)
    assert gx in w.tree_by_x


def test_can_mine_within_two_blocks_not_farther(p: Mc2dParams) -> None:
    from app.games.minecraft_2d_online.manager import Minecraft2DManager, Mc2dPlayer

    mgr = Minecraft2DManager()
    mgr.world.p = p
    pl = Mc2dPlayer(
        username="t",
        in_world=True,
        px=10.0,
        py=0.0,
        stamina=100,
        pickaxe=200,
        inv={},
        dust=0,
        dust_rate=14,
        dust_history=[],
    )
    assert mgr._mine_adjacent(pl, 10, 2)
    assert not mgr._mine_adjacent(pl, 10, 4)
    assert not mgr._mine_adjacent(pl, 10, 0)
    assert mgr._mine_adjacent(pl, 10, -2)
    assert not mgr._mine_adjacent(pl, 10, -3)


def test_apply_world_state(p: Mc2dParams) -> None:
    from app.games.minecraft_2d_online.manager import Minecraft2DManager, Mc2dPlayer

    mgr = Minecraft2DManager()
    mgr.world.p = p
    pl = Mc2dPlayer(
        username="save_u",
        in_world=False,
        px=0.0,
        py=0.0,
        stamina=100,
        pickaxe=200,
        inv={},
        dust=0,
        dust_rate=10,
        dust_history=[],
    )
    loaded = {
        "week_id": mgr.world.week_id,
        "x": 42.5,
        "y": 17.25,
        "inv": {"dirt_block": 3},
        "stamina": 55,
        "pickaxe": 120,
    }
    assert mgr._apply_world_state(pl, loaded)
    assert pl.px == 42.5
    assert pl.py == 17.25
    assert pl.inv.get("dirt_block") == 3
    assert pl.stamina == 55


def test_apple_stamina_gain_30_percent(p: Mc2dParams) -> None:
    from app.games.minecraft_2d_online.manager import Minecraft2DManager

    mgr = Minecraft2DManager()
    mgr.world.p = p
    assert mgr._apple_stamina_gain() == 30


def test_inv_stack_cap_sand_dirt() -> None:
    from app.games.minecraft_2d_online.manager import Mc2dPlayer

    pl = Mc2dPlayer(
        username="t",
        in_world=False,
        px=0.0,
        py=0.0,
        stamina=0,
        pickaxe=0,
        inv={"sand_block": 63},
        dust=0,
        dust_rate=10,
        dust_history=[],
    )
    pl.inv_add("sand_block", 5)
    assert pl.inv["sand_block"] == 64
    pl.inv_add("dirt_block", 100)
    assert pl.inv["dirt_block"] == 64
    pl.inv_add("apple", 100)
    assert pl.inv["apple"] == 64


def test_surface_player_grounded_and_jumps(p: Mc2dParams) -> None:
    from app.games.minecraft_2d_online.manager import Minecraft2DManager, Mc2dPlayer
    from app.games.minecraft_2d_online.tiles import Tile

    mgr = Minecraft2DManager()
    mgr.world.p = p
    ix = 8
    sy = mgr.world.surface_y()
    mgr.world.set_tile(ix, sy, int(Tile.SAND))
    pl = Mc2dPlayer(
        username="t",
        in_world=True,
        px=float(ix),
        py=0.0,
        stamina=100,
        pickaxe=200,
        inv={},
        dust=0,
        dust_rate=14,
        dust_history=[],
    )
    assert mgr._grounded(pl)
    pl.jump_requested = True
    mgr._physics_player(pl, 0.05)
    assert pl.py < -0.2
    for _ in range(40):
        mgr._physics_player(pl, 0.05)
    assert pl.py > -0.15


def test_apple_spawns_beside_tree_not_under_trunk(p: Mc2dParams) -> None:
    from app.games.minecraft_2d_online.world import ChunkWorld
    from app.games.minecraft_2d_online.tiles import Tile

    w = ChunkWorld(p=p)
    w.tree_by_x[10] = 1
    sy = w.surface_y()
    pos = w._pick_apple_spawn(10)
    assert pos is not None
    ax, ay = pos
    assert ax != 10
    assert ay == max(0, sy - 1)
    assert int(w.get_tile(ax, ay)) == Tile.AIR


def test_jump_in_pit_stays_near_pit_not_surface(p: Mc2dParams) -> None:
    from app.games.minecraft_2d_online.manager import Minecraft2DManager, Mc2dPlayer
    from app.games.minecraft_2d_online.tiles import Tile

    mgr = Minecraft2DManager()
    mgr.world.p = p
    ix = 20
    floor_y = 12
    for ty in range(p.sky_rows + p.world_depth_tiles):
        t = Tile.AIR if ty < floor_y else Tile.STONE
        mgr.world.set_tile(ix, ty, int(t))
    pl = Mc2dPlayer(
        username="t",
        in_world=True,
        px=float(ix),
        py=float(floor_y) - 1.0,
        stamina=100,
        pickaxe=200,
        inv={},
        dust=0,
        dust_rate=14,
        dust_history=[],
    )
    assert mgr._grounded(pl)
    pl.jump_requested = True
    for _ in range(30):
        mgr._physics_player(pl, 0.05)
    assert pl.py >= float(floor_y) - 1.0 - 1.55
    assert pl.py > float(p.sky_rows) + 0.5


def test_player_stays_on_grass_under_tree_sprite(p: Mc2dParams) -> None:
    from app.games.minecraft_2d_online.manager import Minecraft2DManager, Mc2dPlayer

    mgr = Minecraft2DManager()
    mgr.world.p = p
    ix = 12
    sy = mgr.world.surface_y()
    mgr.world.set_tile(ix, sy, int(Tile.GRASS))
    mgr.world.tree_by_x[ix] = 2
    for ty in range(sy + 1, p.sky_rows + p.world_depth_tiles):
        mgr.world.set_tile(ix, ty, int(Tile.STONE))
    pl = Mc2dPlayer(
        username="t",
        in_world=True,
        px=float(ix),
        py=0.0,
        stamina=100,
        pickaxe=200,
        inv={},
        dust=0,
        dust_rate=14,
        dust_history=[],
    )
    for _ in range(200):
        mgr._physics_player(pl, 0.05)
    assert mgr._grounded(pl)
    assert pl.py < 0.15
    x0, y0, x1, y1 = mgr._player_aabb(pl)
    assert not mgr._aabb_blocked(x0, y0, x1, y1)


def test_player_stays_on_ground_after_physics(p: Mc2dParams) -> None:
    from app.games.minecraft_2d_online.manager import Minecraft2DManager, Mc2dPlayer

    mgr = Minecraft2DManager()
    mgr.world.p = p
    ix = 10
    for ty in range(p.sky_rows + p.world_depth_tiles):
        t = Tile.STONE if ty >= 1 else Tile.AIR
        mgr.world.set_tile(ix, ty, int(t))
    pl = Mc2dPlayer(
        username="t",
        in_world=True,
        px=float(ix),
        py=0.0,
        stamina=100,
        pickaxe=200,
        inv={},
        dust=0,
        dust_rate=14,
        dust_history=[],
    )
    for _ in range(400):
        mgr._physics_player(pl, 0.05)
    x0, y0, x1, y1 = mgr._player_aabb(pl)
    assert not mgr._aabb_blocked(x0, y0, x1, y1)
    assert mgr._grounded(pl)
    assert pl.py < 0.15


def test_player_pushed_out_of_solid(p: Mc2dParams) -> None:
    from app.games.minecraft_2d_online.manager import Minecraft2DManager, Mc2dPlayer

    mgr = Minecraft2DManager()
    mgr.world.p = p
    ix = 5
    for ty in range(p.sky_rows + p.world_depth_tiles):
        mgr.world.set_tile(ix, ty, int(Tile.STONE if ty >= 1 else Tile.AIR))
    pl = Mc2dPlayer(
        username="t",
        in_world=True,
        px=float(ix),
        py=2.5,
        stamina=100,
        pickaxe=200,
        inv={},
        dust=0,
        dust_rate=14,
        dust_history=[],
    )
    for _ in range(40):
        mgr._resolve_inside_solids(pl, max_push=0.5)
        mgr._snap_to_ground(pl)
    assert not mgr._center_in_solid(pl)
