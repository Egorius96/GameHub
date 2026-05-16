from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Dict, Tuple

from sqlalchemy import text

from app.db.session import engine

_total: Dict[date, int] = {}
_by_path: Dict[Tuple[date, str, str], int] = {}
_lock = asyncio.Lock()
_task: asyncio.Task[None] | None = None


def _today() -> date:
    return datetime.now(timezone.utc).date()


def should_track(method: str, path: str) -> bool:
    # исключаем «шумные» и автоматические запросы
    if path == "/health" or path.startswith("/ws/"):
        return False
    if path.startswith("/api/presence/ping"):
        return False
    return True


async def track(method: str, path: str) -> None:
    d = _today()
    key = (d, method.upper(), path)
    async with _lock:
        _total[d] = int(_total.get(d, 0)) + 1
        _by_path[key] = int(_by_path.get(key, 0)) + 1


async def _flush_once() -> None:
    async with _lock:
        total = dict(_total)
        by_path = dict(_by_path)
        _total.clear()
        _by_path.clear()

    if not total and not by_path:
        return

    with engine().begin() as conn:
        for d, c in total.items():
            conn.execute(
                text(
                    """
                    INSERT INTO request_stats_daily(day, count)
                    VALUES (:day, :count)
                    ON CONFLICT (day) DO UPDATE
                    SET count = request_stats_daily.count + EXCLUDED.count
                    """
                ),
                {"day": d, "count": c},
            )
        for (d, m, p), c in by_path.items():
            conn.execute(
                text(
                    """
                    INSERT INTO request_stats_path(day, method, path, count)
                    VALUES (:day, :method, :path, :count)
                    ON CONFLICT (day, method, path) DO UPDATE
                    SET count = request_stats_path.count + EXCLUDED.count
                    """
                ),
                {"day": d, "method": m, "path": p, "count": c},
            )


async def background_loop() -> None:
    while True:
        await asyncio.sleep(5.0)
        try:
            await _flush_once()
        except Exception:
            # не ломаем сервис из-за статистики
            pass


def start() -> None:
    global _task
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(background_loop(), name="request_stats_flush")


async def stop() -> None:
    global _task
    if _task is None or _task.done():
        _task = None
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None

