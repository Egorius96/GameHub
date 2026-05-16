# Система управления данными пользователей

Проект состоит из бэкенда на FastAPI, базы данных SQLite и фронтенда на React для управления данными пользователей.

## Быстрый старт

Для запуска проекта используйте следующую команду:

```bash
docker-compose up -d --build
```

После запуска сервисы будут доступны по следующим адресам:
- Фронтенд: http://94.159.100.3:3000
- API бэкенда: http://94.159.100.3:7998

## API Эндпоинты

### 1. Создание пользователя
- **URL**: `/users/`
- **Метод**: `POST`
- **Описание**: Создание нового пользователя
- **Тело запроса**:
```json
{
    "username": "john_doe",
    "password": "secret123",
    "project": "project1",
    "other_data": {
        "age": 25,
        "email": "john@example.com",
        "interests": ["coding", "reading"]
    }
}
```
- **Ответ с ошибкой**: `400 Bad Request`
```json
{
    "detail": "Username already exists"
}
```

### 2. Список пользователей
- **URL**: `/users/`
- **Метод**: `GET`
- **Параметры запроса**:
  - `skip`: Количество записей для пропуска (по умолчанию: 0)
  - `limit`: Максимальное количество возвращаемых записей (по умолчанию: 100)
- **Пример**: `GET /users/?skip=0&limit=100`

### 3. Аутентификация пользователя
- **URL**: `/users/auth`
- **Метод**: `POST`
- **Описание**: Получение данных пользователя по логину и паролю
- **Тело запроса**:
```json
{
    "username": "john_doe",
    "password": "secret123"
}
```
- **Ответ с ошибкой**: `401 Unauthorized`
```json
{
    "detail": "Invalid username or password"
}
```

### 4. Обновление пользователя
- **URL**: `/users/update`
- **Метод**: `PUT`
- **Описание**: Обновление данных пользователя (требуется аутентификация)
- **Тело запроса**:
```json
{
    "user_auth": {
        "username": "current_username",
        "password": "current_password"
    },
    "user_update": {
        "username": "new_username",
        "password": "new_password",
        "project": "new_project",
        "other_data": {
            "age": 26,
            "email": "new.email@example.com",
            "interests": ["coding", "reading", "traveling"]
        }
    }
}
```
- **Ответы с ошибками**:
  - `401 Unauthorized`:
  ```json
  {
      "detail": "Invalid username or password"
  }
  ```
  - `400 Bad Request`:
  ```json
  {
      "detail": "Username already exists"
  }
  ```

### 5. Удаление пользователя
- **URL**: `/users/delete`
- **Метод**: `DELETE`
- **Описание**: Удаление пользователя (требуется аутентификация)
- **Тело запроса**:
```json
{
    "username": "john_doe",
    "password": "secret123"
}
```
- **Ответ с ошибкой**: `401 Unauthorized`
```json
{
    "detail": "Invalid username or password"
}
```

## Примеры команд cURL

### Создание пользователя
```bash
curl -X POST "http://94.159.100.3:7998/users/" \
     -H "Content-Type: application/json" \
     -d '{
         "username": "john_doe",
         "password": "secret123",
         "project": "project1",
         "other_data": {
             "age": 25,
             "email": "john@example.com",
             "interests": ["coding", "reading"]
         }
     }'
```

### Список пользователей
```bash
curl "http://94.159.100.3:7998/users/?skip=0&limit=100"
```

### Аутентификация пользователя
```bash
curl -X POST "http://94.159.100.3:7998/users/auth" \
     -H "Content-Type: application/json" \
     -d '{
         "username": "john_doe",
         "password": "secret123"
     }'
```

### Обновление пользователя
```bash
curl -X PUT "http://94.159.100.3:7998/users/update" \
     -H "Content-Type: application/json" \
     -d '{
         "user_auth": {
             "username": "john_doe",
             "password": "secret123"
         },
         "user_update": {
             "username": "john_doe_updated",
             "password": "newpassword",
             "project": "new_project",
             "other_data": {
                 "age": 26,
                 "email": "john.new@example.com",
                 "interests": ["coding", "reading", "traveling"]
             }
         }
     }'
```

### Удаление пользователя
```bash
curl -X DELETE "http://94.159.100.3:7998/users/delete" \
     -H "Content-Type: application/json" \
     -d '{
         "username": "john_doe",
         "password": "secret123"
     }'
``` 