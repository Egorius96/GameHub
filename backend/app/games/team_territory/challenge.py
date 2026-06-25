"""Challenge: режимы 1–3 (п. 5.2 GAME_RULES)."""

from __future__ import annotations

import random
import secrets
import string
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from app.games.team_territory.constants import TeamTerritoryParams

Mode = Literal[1, 2, 3]

SUPPORTED_SPELLING_LOCALES = frozenset({"en", "ru", "it", "es", "de"})

_FALLBACK_WORDS: dict[str, list[str]] = {
    "en": ["game", "play", "book", "tree", "house", "water", "friend", "school", "happy", "music"],
    "ru": ["игра", "дом", "котик", "школа", "друг", "вода", "солнце", "книга", "мячик", "песня"],
    "it": ["gioco", "casa", "scuola", "amico", "acqua", "sole", "libro", "palla", "cane", "gatto"],
    "es": ["juego", "casa", "escuela", "amigo", "agua", "sol", "libro", "pelota", "perro", "gato"],
    "de": ["spiel", "haus", "schule", "freund", "wasser", "sonne", "buch", "ball", "hund", "katze"],
}


def normalize_spelling_locale(lang: str | None) -> str:
    loc = (lang or "en").strip().lower()[:2]
    return loc if loc in SUPPORTED_SPELLING_LOCALES else "en"


def _wordlist_path(params: TeamTerritoryParams, locale: str) -> Path:
    custom = (params.challenge_spelling_wordlist or "").strip()
    if custom and locale == "en":
        return Path(custom)
    base = Path(__file__).resolve().parent
    return base / f"wordlist_{locale}.txt"


def _is_valid_spelling_word(word: str, locale: str) -> bool:
    if len(word) < 4:
        return False
    if locale == "en":
        return all(c in string.ascii_lowercase for c in word)
    if locale == "ru":
        return all(c.isalpha() or c == "ё" for c in word)
    for ch in word:
        if ch == "-":
            continue
        if unicodedata.category(ch) not in ("Ll", "Lu"):
            return False
    return True


def load_spelling_words(params: TeamTerritoryParams, locale: str = "en") -> list[str]:
    loc = normalize_spelling_locale(locale)
    path = _wordlist_path(params, loc)
    if not path.is_file():
        return list(_FALLBACK_WORDS.get(loc, _FALLBACK_WORDS["en"]))
    words: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        w = line.strip().lower()
        if not w or w in seen:
            continue
        if not _is_valid_spelling_word(w, loc):
            continue
        seen.add(w)
        words.append(w)
    if len(words) < 50:
        return list(_FALLBACK_WORDS.get(loc, _FALLBACK_WORDS["en"]))
    return words


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
        a, b = rng.randint(0, 99), rng.randint(0, 99)
        if a < b:
            a, b = b, a
        return f"{a} - {b}", a - b
    a, b = rng.randint(2, 12), rng.randint(2, 12)
    return f"{a} x {b}", a * b


def generate_spelling(words: list[str], rng: random.Random) -> tuple[str, str, str]:
    """Возвращает (display, missing_letter, full_word)."""
    pool = [w for w in words if len(w) >= 4]
    if not pool:
        pool = ["game", "play", "book"]
    w = rng.choice(pool)
    pos = rng.randint(1, len(w) - 2)
    missing = w[pos]
    display = w[:pos] + "_" + w[pos + 1 :]
    return display, missing.lower(), w


def generate_sequence_layout(rng: random.Random) -> list[dict[str, Any]]:
    labels = list(range(1, 11))
    rng.shuffle(labels)
    out: list[dict[str, Any]] = []
    used: list[tuple[float, float]] = []
    for i, lab in enumerate(labels):
        for _ in range(40):
            x = round(rng.uniform(8, 82), 1)
            y = round(rng.uniform(8, 82), 1)
            if all((x - ux) ** 2 + (y - uy) ** 2 >= 12 ** 2 for ux, uy in used):
                used.append((x, y))
                out.append({"id": i, "label": lab, "x": x, "y": y})
                break
        else:
            x = round(10 + (i % 5) * 18, 1)
            y = round(12 + (i // 5) * 22, 1)
            out.append({"id": i, "label": lab, "x": x, "y": y})
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

    def _round_seconds(self) -> int:
        if self.mode == 1:
            return max(1, int(self.params.challenge_math_sec))
        if self.mode == 3:
            return max(1, int(self.params.challenge_sequence_sec))
        return max(1, int(self.params.challenge_riddle_sec))

    def to_public_dict(self, now: datetime) -> dict[str, Any]:
        d: dict[str, Any] = {
            "challenge_id": self.challenge_id,
            "mode": self.mode,
            "round": self.round_index,
            "max_rounds": self.params.challenge_problems,
            "next_round_not_before": self.next_round_not_before.isoformat() if self.next_round_not_before else None,
            "round_deadline_at": self.round_deadline_at.isoformat() if self.round_deadline_at else None,
            "round_seconds": self._round_seconds(),
            "prompt": self.current_prompt,
        }
        if self.mode == 3 and self.sequence_layout:
            d["circles"] = self.sequence_layout
            d["sequence_next"] = self.sequence_next
        return d

    def start_round(self, now: datetime) -> None:
        self.next_round_not_before = None
        sec = self._round_seconds()
        if self.mode in (1, 2):
            if self.mode == 1:
                expr, ans = generate_math_problem(self.rng)
                self.current_prompt = expr + " = ?"
                self.current_answer = str(int(ans))
            else:
                display, miss, _full = generate_spelling(self.words, self.rng)
                self.current_prompt = display
                self.current_answer = miss
            self.round_deadline_at = now + timedelta(seconds=sec)
        else:
            self.sequence_layout = generate_sequence_layout(self.rng)
            self.sequence_next = 1
            self.round_deadline_at = now + timedelta(seconds=sec)

    def after_round_gap(self, now: datetime) -> None:
        self.next_round_not_before = now + timedelta(seconds=self.params.challenge_round_gap_sec)
        self.round_deadline_at = None
        self.current_prompt = None
        self.current_answer = None
        self.sequence_layout = None
        self.sequence_next = 1
