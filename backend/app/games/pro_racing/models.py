from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Direction = Literal["up", "down", "left", "right", "stop"]


@dataclass
class Entity:
    x: float
    y: float
    w: float
    h: float


@dataclass
class PlayerState:
    x: float
    y: float
    lives: int = 3
    direction: Direction = "stop"
    move_x: int = 0
    move_y: int = 0


@dataclass
class GameState:
    mode: str
    seconds: int = 0
    frame: int = 0
    speed_rock: float = 10.0
    width: int = 1200
    height: int = 700
    player1: PlayerState = field(default_factory=lambda: PlayerState(50, 300))
    player2: PlayerState = field(default_factory=lambda: PlayerState(50, 450))
    rock1: Entity = field(default_factory=lambda: Entity(1200, 200, 100, 80))
    rock2: Entity = field(default_factory=lambda: Entity(1700, 500, 100, 80))
    diamond: Entity = field(default_factory=lambda: Entity(-200, -200, 100, 60))
    diamond_cd: int = 0
    game_over: bool = False
    persisted: bool = False
    winner: str | None = None
    hard_modifier: str | None = None
    diamonds_collected: int = 0
    drugs_limit: int = 5
    rockspeed_limit: int = 1
    immue_until: float = 0.0
    hearty_ready: bool = False
