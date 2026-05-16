from __future__ import annotations

from app.games.pro_racing.engine import GameEngine


class SessionManager:
    def __init__(self) -> None:
        self.sessions: dict[str, GameEngine] = {}

    def create(self, key: str, mode: str, car_level: int) -> GameEngine:
        engine = GameEngine(mode=mode, car_level=car_level)
        self.sessions[key] = engine
        return engine

    def get(self, key: str) -> GameEngine | None:
        return self.sessions.get(key)

    def remove(self, key: str) -> None:
        self.sessions.pop(key, None)


session_manager = SessionManager()
