"""Команды и цвета (п. 2 GAME_RULES)."""

from __future__ import annotations

MAX_PLAYERS_PER_TEAM = 4
MAX_PLAYERS_IN_LOBBY = 16

TEAM_COLORS: list[dict[str, str]] = [
    {"id": 0, "name": "Красные", "key": "red", "hex": "#e53935"},
    {"id": 1, "name": "Синие", "key": "blue", "hex": "#1e88e5"},
    {"id": 2, "name": "Зелёные", "key": "green", "hex": "#43a047"},
    {"id": 3, "name": "Жёлтые", "key": "yellow", "hex": "#f9a825"},
]


def team_count_bounds() -> tuple[int, int]:
    return 4, 4


def assign_team_id(join_order: int, num_teams: int) -> int:
    """Round-robin по командам 0..num_teams-1."""
    if num_teams < 2:
        return 0
    return join_order % num_teams


def teams_public_meta(num_teams: int) -> list[dict]:
    return [dict(TEAM_COLORS[i]) for i in range(min(num_teams, len(TEAM_COLORS)))]
