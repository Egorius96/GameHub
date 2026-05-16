"""Challenge: режимы 1–3 (п. 5.2 GAME_RULES)."""

from __future__ import annotations

import secrets
import string
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from app.games.team_territory.constants import TeamTerritoryParams

Mode = Literal[1, 2, 3]


def _wordlist_path(params: TeamTerritoryParams) -> Path:
    p = (params.challenge_spelling_wordlist or "").strip()
    if p:
        return Path(p)
    return Path(__file__).resolve().parent / "wordlist_en.txt"


def load_spelling_words(params: TeamTerritoryParams) -> list[str]:
    path = _wordlist_path(params)
    if not path.is_file():
        return ["word", "game", "play", "grid", "team", "cell", "paint", "tick", "match", "lobby"]
    words: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        w = line.strip().lower()
        if len(w) >= 4 and all(c in string.ascii_lowercase for c in w):
            words.append(w)
    return words if len(words) >= 100 else ["word", "game", "play", "grid", "team"]


def pick_mode(params: TeamTerritoryParams, rng: random.Random) -> Mode:
    w1 = max(0.0, params.challenge_weight_math)
    w2 = max(0.0, params.challenge_weight_spelling)
    w3 = max(0.0, params.challenge_weight_sequence)
    s = w1 + w2 + w3
    if s <= 0:
        return 1
    r = rng.random() * s
    if r < w1:
        return 1
    if r < w1 + w2:
        return 2
    return 3


def generate_math_problem(rng: random.Random) -> tuple[str, int]:
    op = rng.choice(["+", "-", "*"])
    if op == "+":
        a, b = rng.randint(0, 99), rng.randint(0, 99)
        return f"{a} + {b}", a + b
    if op == "-":
        a, b = rng.randint(20, 120), rng.randint(0, 80)
        return f"{a} - {b}", a - b
    a, b = rng.randint(2, 12), rng.randint(2, 12)
    return f"{a} x {b}", a * b


def generate_spelling(words: list[str], rng: random.Random) -> tuple[str, str, str]:
    """Возвращает (display, missing_letter, full_word)."""
    w = rng.choice(words)
    if len(w) < 4:
        w = "wordgame"
    # пропуск не на первом и не на последнем (рекомендация ТЗ)
    pos = rng.randint(1, len(w) - 2)
    missing = w[pos]
    display = w[:pos] + "_" + w[pos + 1 :]
    return display, missing.lower(), w


def generate_sequence_layout(rng: random.Random) -> list[dict[str, Any]]:
    labels = list(range(1, 11))
    rng.shuffle(labels)
    out: list[dict[str, Any]] = []
    for i, lab in enumerate(labels):
        out.append({"id": i, "label": lab})
    return out


@dataclass
class ChallengeSession:
    challenge_id: str
    username: str
    mode: Mode
    params: TeamTerritoryParams
    started_at_utc: datetime
    round_index: int = 1  # 1..5
    next_round_not_before: datetime | None = None
    round_deadline_at: datetime | None = None
    # mode 1–2
    current_prompt: str | None = None
    current_answer: str | None = None  # string for compare
    # mode 3
    sequence_layout: list[dict[str, Any]] | None = None
    sequence_next: int = 1
    words: list[str] = field(default_factory=list)
    rng: random.Random = field(default_factory=lambda: random.Random(secrets.randbits(128)))

    def to_public_dict(self, now: datetime) -> dict[str, Any]:
        d: dict[str, Any] = {
            "challenge_id": self.challenge_id,
            "mode": self.mode,
            "round": self.round_index,
            "max_rounds": self.params.challenge_problems,
            "next_round_not_before": self.next_round_not_before.isoformat() if self.next_round_not_before else None,
            "round_deadline_at": self.round_deadline_at.isoformat() if self.round_deadline_at else None,
            "prompt": self.current_prompt,
        }
        if self.mode == 3 and self.sequence_layout:
            d["circles"] = self.sequence_layout
            d["sequence_next"] = self.sequence_next
        return d

    def start_round(self, now: datetime) -> None:
        self.next_round_not_before = None
        p = self.params
        if self.mode in (1, 2):
            if self.mode == 1:
                expr, ans = generate_math_problem(self.rng)
                self.current_prompt = expr + " = ?"
                self.current_answer = str(int(ans))
            else:
                display, miss, _full = generate_spelling(self.words, self.rng)
                self.current_prompt = display
                self.current_answer = miss
            self.round_deadline_at = now + timedelta(seconds=p.challenge_riddle_sec)
        else:
            self.sequence_layout = generate_sequence_layout(self.rng)
            self.sequence_next = 1
            self.round_deadline_at = now + timedelta(seconds=p.challenge_riddle_sec)

    def after_round_gap(self, now: datetime) -> None:
        self.next_round_not_before = now + timedelta(seconds=self.params.challenge_round_gap_sec)
        self.round_deadline_at = None
        self.current_prompt = None
        self.current_answer = None
        self.sequence_layout = None
        self.sequence_next = 1
