from __future__ import annotations

from dataclasses import dataclass
from time import time


@dataclass
class PresenceState:
    last_seen_ts: float
    game: str | None


class PresenceRegistry:
    def __init__(self) -> None:
        self._by_username: dict[str, PresenceState] = {}

    def touch(self, username: str, game: str | None = None) -> None:
        now = time()
        prev = self._by_username.get(username)
        if prev is None:
            self._by_username[username] = PresenceState(last_seen_ts=now, game=game)
            return
        prev.last_seen_ts = now
        if game is not None:
            prev.game = game

    def forget(self, username: str) -> None:
        """Убрать пользователя из реестра (удаление аккаунта и т.п.)."""
        self._by_username.pop(username, None)

    def prune(self, online_seconds: int = 60) -> None:
        now = time()
        dead = [u for u, st in self._by_username.items() if (now - st.last_seen_ts) > online_seconds]
        for u in dead:
            self._by_username.pop(u, None)

    def snapshot(self, online_seconds: int = 60) -> dict:
        self.prune(online_seconds=online_seconds)
        now = time()
        online_users: list[str] = []
        by_game: dict[str, int] = {}
        for username, st in self._by_username.items():
            if username == "admindb":
                continue
            if (now - st.last_seen_ts) <= online_seconds:
                online_users.append(username)
                if st.game:
                    by_game[st.game] = by_game.get(st.game, 0) + 1
        online_users.sort(key=lambda s: s.lower())
        return {
            "online_total": len(online_users),
            "online_users": online_users,
            "by_game": by_game,
            "online_seconds": online_seconds,
        }


presence = PresenceRegistry()

