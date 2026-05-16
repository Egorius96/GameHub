"""Идентификаторы тайлов (§13.3, §13.7)."""

from __future__ import annotations

from enum import IntEnum


class Tile(IntEnum):
    AIR = 0
    SAND = 1
    DIRT = 2
    STONE = 3
    IRON = 4
    DIAMOND = 5
    GRASS = 6
    TREE = 7


def is_solid(t: int) -> bool:
    return t in (Tile.SAND, Tile.DIRT, Tile.STONE, Tile.IRON, Tile.DIAMOND)


def is_passable_decor(t: int) -> bool:
    return t in (Tile.GRASS, Tile.TREE)


def blocks_movement(t: int) -> bool:
    """Коллизия только у твёрдых блоков и травы; деревья — отдельные спрайты без тайла."""
    return is_solid(t) or t == Tile.GRASS


def normalize_tile(t: int) -> int:
    """Старые чанки с TILE.TREE → песок под спрайтом дерева."""
    return int(Tile.SAND) if int(t) == int(Tile.TREE) else int(t)


def mineable(t: int) -> bool:
    """Деревья §13.7 не рубим в v1; трава ломается без дропа."""
    return is_solid(t) or t == Tile.GRASS


PLACEABLE_ITEMS: dict[str, Tile] = {
    "sand_block": Tile.SAND,
    "dirt_block": Tile.DIRT,
    "stone_block": Tile.STONE,
}

_STACK_CAPS: dict[str, int] = {
    "sand_block": 64,
    "dirt_block": 64,
    "apple": 64,
}


def inv_stack_cap(item_key: str) -> int | None:
    return _STACK_CAPS.get(item_key)


def tile_mine_drop(t: int) -> str | None:
    return {
        int(Tile.SAND): "sand_block",
        int(Tile.DIRT): "dirt_block",
        int(Tile.STONE): "stone_block",
        int(Tile.IRON): "iron_block",
        int(Tile.DIAMOND): "raw_diamond",
    }.get(int(t))


def is_refill_source(t: int) -> bool:
    return t in (Tile.SAND, Tile.DIRT)
