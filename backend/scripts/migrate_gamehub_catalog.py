"""
Миграция каталога пользователя gamehub_catalog: дописывает недостающие игры
из app.services.catalog.default_catalog_other_data (в т.ч. tamagochi_world_game).

Запуск из каталога backend:
  python scripts/migrate_gamehub_catalog.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.catalog import migrate_catalog_missing_games  # noqa: E402


def main() -> int:
    result = migrate_catalog_missing_games()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
