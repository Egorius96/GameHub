from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UserSession:
    username: str
    password: str
    user: dict


sessions: dict[str, UserSession] = {}
