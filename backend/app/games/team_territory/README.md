# Team Territory

Серверная игра по [`GAME_RULES.md`](./GAME_RULES.md).

## Env (основные)

| Переменная | Смысл |
|------------|--------|
| `GAMEHUB_ENV` | `development` (по умолчанию) или `production` |
| `TEAM_TERRITORY_DEBUG_SOLO_LOBBY` | `1` только в dev — старт матча в одиночку; **в production с `GAMEHUB_ENV=production` запуск API падает** |
| `TEAM_TERRITORY_MAX_GRID_G` | Верхний предел G (по умолчанию 18) |
| `TT_TICK_MS`, `TT_MATCH_MAX_SEC`, `TT_MATCH_STALL_IDLE_SEC`, … | см. `app/core/config.py` |

## Чеклист перед продом

1. `GAMEHUB_ENV=production`
2. `TEAM_TERRITORY_DEBUG_SOLO_LOBBY` не установлен или `0`
3. Убедиться, что в UI нет баннера DEBUG solo

## WebSocket

`GET /ws/team-territory?token=JWT&room_id=default`

Сообщения клиента: `set_ready`, `claim`, `buy_paint`, `challenge_start`, `challenge_submit`, `reset_to_lobby`, `set_num_teams`.

## Словарь Challenge (режим 2)

Файл `wordlist_en.txt` в этом каталоге (≥1000 слов). Путь переопределяется `TT_CHALLENGE_SPELLING_WORDLIST`.
