## Игра: “Галочки 10×10”

Цель: быстрее соперников заполнить поле 10×10 своими галочками, ограниченными ресурсом, который пополняется по времени.

---

## Термины и сущности

- **Поле**: сетка 10×10 (100 клеток).
- **Игрок**: идентификатор `player_id`.
- **Галочка**: действие “поставить метку” в клетку.
- **Ресурс**: “галочки в запасе” (сколько раз игрок может поставить галочку прямо сейчас).
- **Тик пополнения**: раз в час игроку начисляется +5 галочек.

---

## Правила (подробно)

### Состояние матча

- Матч создаётся с набором игроков (обычно 2, но можно N).
- У каждого игрока есть:
  - `available_checks`: текущее число галочек, которые можно потратить.
  - `last_refill_at`: время последнего учтённого пополнения.
  - `cells_marked`: сколько клеток игрок уже занял.
- Поле хранит владельца клетки: пусто или `player_id`.

### Пополнение ресурса

- Каждые 60 минут игрок получает **+5** к `available_checks`.
- Пополнение считается “лениво”: при любом запросе от игрока (или при вызове `tick(now)`) мы пересчитываем, сколько полных часов прошло с `last_refill_at`, и начисляем \(hours * 5\).
- Опционально (по умолчанию включено в коде): **кап** запаса `max_available_checks`, чтобы нельзя было копить бесконечно.

### Ход (постановка галочки)

- Игрок выбирает клетку \((x, y)\), где \(0 \le x,y < 10\).
- Условия успешного хода:
  - у игрока `available_checks >= cost_per_mark` (по умолчанию 1);
  - клетка свободна;
  - матч в статусе `in_progress`.
- При успехе:
  - из `available_checks` вычитается стоимость;
  - клетка помечается владельцем `player_id`;
  - увеличивается `cells_marked`.

### Ограничения и защита от “гонок”

- Повторная постановка в уже занятую клетку запрещена (ошибка).
- Один ход = одна клетка (пакетные ходы можно добавить отдельным методом позже).
- Для серверной реализации: проверка и применение хода должны быть **атомарными** на стороне сервера (чтобы два игрока не заняли одну клетку одновременно).

### Победа и окончание матча

- **Победа**: игрок, который первым достиг `cells_marked == 100`, выигрывает.
- **Ничья** (если нужна): если последний свободный слот заняли разные игроки “одновременно”, на сервере это решается порядком обработки событий. Если хотите честную ничью — вводится “окно” \(например, 200мс\) и сравнение `finished_at`; по умолчанию в базовых правилах **ничьи нет**, есть порядок.
- После победы матч переходит в `finished`, и новые ходы отклоняются.

---

## Базовый Python-класс (каркас)

Ниже — минимальная модель, пригодная для интеграции в backend-authoritative сервер: хранит состояние, начисляет ресурс по времени, валидирует и применяет ходы, определяет победителя.

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, Iterable, List, Optional, Tuple


class GameStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"


@dataclass(slots=True)
class PlayerState:
    player_id: str
    available_checks: int
    last_refill_at: datetime
    cells_marked: int = 0


@dataclass(slots=True)
class MarkResult:
    ok: bool
    reason: Optional[str] = None
    winner_id: Optional[str] = None


class Checkmarks10x10Game:
    """
    Серверная модель игры.

    - Не содержит I/O и сетевого кода.
    - Время передаётся извне (now) для тестируемости и синхронизации с сервером.
    """

    width: int = 10
    height: int = 10

    def __init__(
        self,
        player_ids: Iterable[str],
        *,
        started_at: Optional[datetime] = None,
        initial_checks: int = 5,
        refill_every: timedelta = timedelta(hours=1),
        refill_amount: int = 5,
        cost_per_mark: int = 1,
        max_available_checks: int = 50,
    ) -> None:
        now = started_at or datetime.now(timezone.utc)
        ids = list(player_ids)
        if not ids:
            raise ValueError("player_ids must be non-empty")
        if len(set(ids)) != len(ids):
            raise ValueError("player_ids must be unique")
        if initial_checks < 0:
            raise ValueError("initial_checks must be >= 0")
        if refill_amount <= 0:
            raise ValueError("refill_amount must be > 0")
        if cost_per_mark <= 0:
            raise ValueError("cost_per_mark must be > 0")
        if max_available_checks < 0:
            raise ValueError("max_available_checks must be >= 0")
        if refill_every.total_seconds() <= 0:
            raise ValueError("refill_every must be > 0")

        self.started_at = now
        self.status: GameStatus = GameStatus.IN_PROGRESS
        self.winner_id: Optional[str] = None

        self.refill_every = refill_every
        self.refill_amount = refill_amount
        self.cost_per_mark = cost_per_mark
        self.max_available_checks = max_available_checks

        self.players: Dict[str, PlayerState] = {
            pid: PlayerState(
                player_id=pid,
                available_checks=min(initial_checks, max_available_checks)
                if max_available_checks > 0
                else initial_checks,
                last_refill_at=now,
            )
            for pid in ids
        }

        # board[y][x] -> owner player_id or None
        self.board: List[List[Optional[str]]] = [
            [None for _ in range(self.width)] for _ in range(self.height)
        ]

    def tick(self, now: datetime) -> None:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        for pid in list(self.players.keys()):
            self._apply_refill(pid, now)

    def mark(self, player_id: str, x: int, y: int, *, now: datetime) -> MarkResult:
        if now.tzinfo is None:
            return MarkResult(ok=False, reason="now must be timezone-aware")
        if self.status != GameStatus.IN_PROGRESS:
            return MarkResult(ok=False, reason="game is not in progress", winner_id=self.winner_id)
        if player_id not in self.players:
            return MarkResult(ok=False, reason="unknown player")
        if not (0 <= x < self.width and 0 <= y < self.height):
            return MarkResult(ok=False, reason="out of bounds")

        self._apply_refill(player_id, now)
        ps = self.players[player_id]

        if ps.available_checks < self.cost_per_mark:
            return MarkResult(ok=False, reason="not enough checks")
        if self.board[y][x] is not None:
            return MarkResult(ok=False, reason="cell already marked")

        ps.available_checks -= self.cost_per_mark
        self.board[y][x] = player_id
        ps.cells_marked += 1

        if ps.cells_marked >= self.width * self.height:
            self.status = GameStatus.FINISHED
            self.winner_id = player_id
            return MarkResult(ok=True, winner_id=player_id)

        return MarkResult(ok=True)

    def get_cell_owner(self, x: int, y: int) -> Optional[str]:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError("out of bounds")
        return self.board[y][x]

    def snapshot(self) -> dict:
        return {
            "status": self.status.value,
            "winner_id": self.winner_id,
            "players": {
                pid: {
                    "available_checks": ps.available_checks,
                    "last_refill_at": ps.last_refill_at.isoformat(),
                    "cells_marked": ps.cells_marked,
                }
                for pid, ps in self.players.items()
            },
            "board": self.board,
        }

    def _apply_refill(self, player_id: str, now: datetime) -> None:
        ps = self.players[player_id]
        if now <= ps.last_refill_at:
            return

        elapsed = now - ps.last_refill_at
        period_seconds = self.refill_every.total_seconds()
        hours = int(elapsed.total_seconds() // period_seconds)
        if hours <= 0:
            return

        gained = hours * self.refill_amount
        if self.max_available_checks > 0:
            ps.available_checks = min(self.max_available_checks, ps.available_checks + gained)
        else:
            ps.available_checks += gained

        ps.last_refill_at = ps.last_refill_at + timedelta(seconds=hours * period_seconds)
```

