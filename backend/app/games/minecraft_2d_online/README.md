# Minecraft 2D Online (backend)

Ключ игры: `minecraft_2d_online` (см. `Settings.minecraft_2d_online_game_key`).

## Env (префикс `MC2D_`)

| Переменная | Смысл |
|------------|--------|
| `MC2D_AUTHOR` | Пароль «я автор» для карточки в каталоге (как у других игр) |
| `MC2D_WORLD_WIDTH_TILES` | Ширина мира в тайлах (по умолчанию от `MC2D_SURFACE_RUN_SEC` × `MC2D_PLAYER_TILES_PER_SEC`) |
| `MC2D_WORLD_DEPTH_TILES` | Глубина |
| `MC2D_CHUNK_SIZE` | Размер чанка |
| `MC2D_MAX_IN_WORLD` | Лимит игроков в мире (10) |
| `MC2D_WORLD_TICK_MS` | Период тика засыпания / регенера |
| `MC2D_BASE_CENTER_X` | Центр зоны базы по X (пусто = середина мира) |

Полный список см. `constants.py` / `mc2d_params()`.

## API

- `GET /api/minecraft-2d-online/health` — с сессией  
- `GET /api/minecraft-2d-online/lobby` — снапшот лобби  
- `GET /api/minecraft-2d-online/chunks?cx=&cy=&r=` — тайлы чанков  

WebSocket: `/ws/minecraft-2d-online?token=...`

## Прогресс пользователя

`other_data.games.minecraft_2d_online`: `diamond_dust`, `dust_exchange_rate`, `dust_rate_history`, `exchange_idempotency`, `deliver_idempotency`, `playtime`.

Инвентарь в сессии мира хранится в памяти до выхода из мира.

## Графика (клиент)

Статика: `frontend/public/games/mc2d/atlas.webp` (тайлы 32×32 в ряд по `Tile` id) и `player.webp`. Пересборка из папки с исходниками: `python3 scripts/build_mc2d_atlas.py` (корень репозитория).
