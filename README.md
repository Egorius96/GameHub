# GameHub

## Запуск

```bash
docker compose up --build -d
```

После запуска:
- Сайт: **http://localhost:<HTTP_HOST_PORT>/** (nginx проксирует фронт и API; по умолчанию порт берётся из `.env`).

## Админка GameHub

- **Логин**: `admindb`
- **Пароль**: переменная окружения `ADMINDB_PASSWORD` (в `.env`)
- После входа пользователь `admindb` попадает в `/admin`.

## Отдельная база legacy `users` (не GameHub)

В PostgreSQL хранятся **две разные** таблицы пользователей:

| Таблица | Назначение | Вход на сайте | API |
|---------|------------|---------------|-----|
| `gamehub_users` | Аккаунты GameHub (хаб, игры, мессенджер) | обычная регистрация / вход | `/api/auth/...` |
| `users` | Legacy: старые игры и внешние проекты (бывший SQLite-сервис) | служебный вход `database` | `/users/...` и `/api/admin/users` |

Не путайте их: запись в `users` **не даёт** доступ к GameHub, и наоборот.

Базовый URL для примеров ниже: `http://localhost:<HTTP_HOST_PORT>` (порт из `.env`, например `3000`).

### UI (страница «Users Data»)

- На странице входа GameHub: **логин** `database`, **пароль** `database`
- После входа открывается **/database** — CRUD по таблице `users`

Имена `admindb` и `database` **нельзя** зарегистрировать как обычный аккаунт GameHub.

### HTTP API без UI (совместимость со старым сервисом `:7998`)

Эндпоинты проксируются nginx по пути **`/users/`** (не `/api/users/`). Поведение как у отдельного `db_users_project`: работают только с таблицей **`users`**.

**Создать запись**

```bash
curl -s -X POST "http://localhost:3000/users/" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "john_doe",
    "password": "secret123",
    "project": "misha_pro_racing_game",
    "other_data": {"age": 25}
  }'
```

**Список** (без авторизации)

```bash
curl -s "http://localhost:3000/users/?skip=0&limit=100"
```

**Проверка логина / получить свою запись**

```bash
curl -s -X POST "http://localhost:3000/users/auth" \
  -H "Content-Type: application/json" \
  -d '{"username": "john_doe", "password": "secret123"}'
```

**Изменить** (нужны логин и пароль того пользователя, которого меняете)

```bash
curl -s -X PUT "http://localhost:3000/users/update" \
  -H "Content-Type: application/json" \
  -d '{
    "user_auth": {"username": "john_doe", "password": "secret123"},
    "user_update": {
      "password": "newpass",
      "other_data": {"age": 26}
    }
  }'
```

**Удалить** (логин и пароль удаляемого пользователя)

```bash
curl -s -X DELETE "http://localhost:3000/users/delete" \
  -H "Content-Type: application/json" \
  -d '{"username": "john_doe", "password": "newpass"}'
```

**Пользователи одного проекта** (`POST /users/get_users_by_project`) — как в старой версии: по логину/паролю определяется `project`, возвращаются все записи из `users` с тем же `project` (в ответе `username` и `other_data`, без паролей).

```bash
curl -s -X POST "http://localhost:3000/users/get_users_by_project" \
  -H "Content-Type: application/json" \
  -d '{"username": "john_doe", "password": "newpass"}'
```

Для старых клиентов достаточно заменить хост `http://...:7998/users/` на `http://<ваш-хост>:<HTTP_HOST_PORT>/users/`.

### Админский CRUD по `id` (как UI `/database`)

Тот же токен, что и для страницы `/database`: вход `database` / `database` (или `admindb` с `ADMINDB_PASSWORD`).

```bash
# токен
TOKEN=$(curl -s -X POST "http://localhost:3000/api/auth/sign-in" \
  -H "Content-Type: application/json" \
  -d '{"username":"database","password":"database"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# список
curl -s "http://localhost:3000/api/admin/users?limit=500" \
  -H "Authorization: Bearer $TOKEN"

# создать
curl -s -X POST "http://localhost:3000/api/admin/users" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"username":"p1","password":"pass","project":"my_game","other_data":{}}'

# изменить по id
curl -s -X PUT "http://localhost:3000/api/admin/users/1" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project":"new_project"}'

# удалить по id
curl -s -X DELETE "http://localhost:3000/api/admin/users/1" \
  -H "Authorization: Bearer $TOKEN"
```

Лидерборд GameHub (`/api/leaderboard`) использует **`gamehub_users`**, а не legacy `/users/` — для него отдельный контур.

## Остановка

```bash
docker compose down
```
