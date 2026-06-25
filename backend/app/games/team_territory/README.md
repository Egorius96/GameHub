# Team Territory

Серверная игра по [`GAME_RULES.md`](./GAME_RULES.md).

## Env (основные)

| Переменная | Смысл |
|------------|--------|
| `GAMEHUB_ENV` | `development` (по умолчанию) или `production` |
| `TEAM_TERRITORY_DEBUG_SOLO_LOBBY` | `1` только в dev — старт матча в одиночку; **в production с `GAMEHUB_ENV=production` запуск API падает** |
| `TEAM_TERRITORY_MAX_GRID_G` | Верхний предел G (по умолчанию 18) |
| `TT_TICK_MS`, `TT_MATCH_MAX_SEC`, `TT_MATCH_STALL_IDLE_SEC`, … | см. `app/core/config.py` |
| `TT_CHALLENGE_MATH_SEC` | Таймер challenge «Примеры» (по умолчанию 7 с) |
| `TT_CHALLENGE_RIDDLE_SEC` | Таймер challenge «Слова» (по умолчанию 5 с) |
| `TT_CHALLENGE_SEQUENCE_SEC` | Таймер challenge «Порядок» (по умолчанию 8 с) |
| `TT_COMBO_BONUS_POINTS` | Бонус к итоговому счёту за каждую комбинацию «3 в ряд» (по умолчанию 1) |

## Комбо «три в ряд»

Горизонталь, вертикаль или диагональ из 3 клеток одной команды даёт +`TT_COMBO_BONUS_POINTS` к итоговому счёту при определении победителя. Клетки комбо подсвечиваются и не принимают новые заявки.

## Баланс команд

- Старт матча запрещён, если разница числа игроков между командами **≥ 2** (`lobby_teams_imbalanced` в snapshot, ошибка `teams_imbalanced` при `set_ready`).
- Командам с меньшим составом начисляется бонус к территории: `territory × (max_team_size / team_size − 1)` (поле `balance_bonus` в финальном snapshot).

## Награды алмазами

- Победа: +`TT_WIN_DIAMONDS` (50) каждому игроку команды-победителя.
- Поражение: +`TT_LOSS_DIAMONDS` (10) каждому игроку проигравшей команды.
- Ничья по счёту: +`TT_TIE_DIAMONDS` (10) каждому участнику с достаточной активностью.
- Простой (`stale_idle`): **0** всем, матч считается фейковым.

## Чеклист перед продом

1. `GAMEHUB_ENV=production`
2. `TEAM_TERRITORY_DEBUG_SOLO_LOBBY` не установлен или `0`
3. Убедиться, что в UI нет баннера DEBUG solo

## WebSocket

`GET /ws/team-territory?token=JWT&room_id=default`

Сообщения клиента: `set_ready`, `set_team`, `claim`, `buy_paint`, `challenge_start`, `challenge_submit`, `reset_to_lobby`, `set_num_teams`.

## Словарь Challenge (режим 2)

Файлы `wordlist_{en,ru,it,es,de}.txt` в этом каталоге (~300 простых слов, длина ≥4). Язык слов = `ui_lang` игрока при старте challenge. Путь для en переопределяется `TT_CHALLENGE_SPELLING_WORDLIST`.

Источник слов: curated list на базе частотных английских лемм (проектный файл, без дубликатов).
