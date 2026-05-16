from __future__ import annotations

import random
from typing import Literal

Move = Literal["rock", "paper", "scissors"]

BEATS: dict[Move, Move] = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
ALL_MOVES: tuple[Move, ...] = ("rock", "paper", "scissors")


def normalize_move(s: str) -> Move | None:
    v = str(s or "").strip().lower()
    if v in ALL_MOVES:
        return v  # type: ignore[return-value]
    return None


def outcome(a: Move, b: Move) -> int:
    """1 если a побеждает, -1 если b, 0 — ничья."""
    if a == b:
        return 0
    if BEATS[a] == b:
        return 1
    return -1


def random_move() -> Move:
    return random.choice(ALL_MOVES)
