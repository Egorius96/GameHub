# GameHub

## Запуск

```bash
docker compose up --build -d
```

После запуска:
- Сайт: **http://localhost:<HTTP_HOST_PORT>/** (nginx проксирует фронт и API; по умолчанию порт берётся из `.env`).

## Админка

- **Логин**: `admindb`
- **Пароль**: переменная окружения `ADMINDB_PASSWORD` (в `.env`)
- После входа пользователь `admindb` попадает в `/admin`.

## Остановка

```bash
docker compose down
```
