## Мини‑бекенд для урока: концепция backend‑authoritative Pro Racing

Цель: на уроке за 30–60 минут показать **ключевую идею** — клиент (браузер) отправляет только **ввод** (нажатия), а сервер хранит **истину** (позиции, столкновения, очки) и рассылает состояние всем игрокам.

Ниже — **упрощённая имитация**. Это не прод‑код и не наша текущая реализация — это “демо”, которое легко объяснить и быстро запустить.

---

## Что будет в демо

- **REST**
  - `GET /health` — проверить, что сервер жив
  - `POST /auth/mock_login` — “логин” без БД (возвращает token)
- **WebSocket**
  - `WS /ws/game?token=...&room=...` — комната игры
  - события от клиента: `input.move` (`left/right/up/down/stop`)
  - события от сервера: `state.tick` (позиции/score/seconds), `state.game_over`
- **Память сервера**
  - комнаты и их состояние в dict (без базы)
  - “online” можно показать как last_seen по token (доп. задача)

---

## Минимальная модель игры (очень упрощённо)

- поле: ширина 1200, высота 700
- игрок: прямоугольник 60×30
- камень: прямоугольник 80×60, летит вниз
- алмаз: прямоугольник 50×30, летит вниз
- правило:
  - столкнулся с камнем → lives–1
  - поймал алмаз → diamonds+1
  - выжил N секунд → score растёт по времени

---

## Один файл демо‑бекенда (FastAPI + WebSocket)

Скопируй как `demo_backend.py` и запусти.

```python
import asyncio
import secrets
import time
from dataclasses import dataclass, asdict
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Pro Racing demo backend")


@app.get("/health")
def health():
    return {"ok": True}


class LoginReq(BaseModel):
    username: str


TOKENS: Dict[str, str] = {}  # token -> username


@app.post("/auth/mock_login")
def mock_login(payload: LoginReq):
    if not payload.username:
        raise HTTPException(400, "username required")
    token = secrets.token_urlsafe(16)
    TOKENS[token] = payload.username
    return {"token": token, "username": payload.username}


W = 1200
H = 700


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    def intersects(self, other: "Rect") -> bool:
        return not (
            self.x + self.w < other.x
            or other.x + other.w < self.x
            or self.y + self.h < other.y
            or other.y + other.h < self.y
        )


@dataclass
class RoomState:
    started_at: float
    last_tick: float
    seconds: int
    lives: int
    diamonds: int
    player: Rect
    rock: Rect
    diamond: Rect
    move: str  # left/right/up/down/stop
    game_over: bool


ROOMS: Dict[str, RoomState] = {}


def _reset_room(room: str) -> RoomState:
    now = time.time()
    st = RoomState(
        started_at=now,
        last_tick=now,
        seconds=0,
        lives=3,
        diamonds=0,
        player=Rect(x=200, y=500, w=60, h=30),
        rock=Rect(x=500, y=-80, w=80, h=60),
        diamond=Rect(x=800, y=-50, w=50, h=30),
        move="stop",
        game_over=False,
    )
    ROOMS[room] = st
    return st


def _step(st: RoomState, dt: float) -> None:
    # движение игрока по последней команде
    speed = 360.0  # px/sec
    if st.move == "left":
        st.player.x -= speed * dt
    elif st.move == "right":
        st.player.x += speed * dt
    elif st.move == "up":
        st.player.y -= speed * dt
    elif st.move == "down":
        st.player.y += speed * dt

    # clamp в поле
    st.player.x = max(0, min(W - st.player.w, st.player.x))
    st.player.y = max(0, min(H - st.player.h, st.player.y))

    # падение объектов
    st.rock.y += 420.0 * dt
    st.diamond.y += 360.0 * dt

    # респавн сверху
    if st.rock.y > H + 50:
        st.rock.y = -80
        st.rock.x = float(secrets.randbelow(W - int(st.rock.w)))
    if st.diamond.y > H + 50:
        st.diamond.y = -50
        st.diamond.x = float(secrets.randbelow(W - int(st.diamond.w)))

    # коллизии
    if st.player.intersects(st.rock):
        st.lives -= 1
        st.rock.y = -80
        st.rock.x = float(secrets.randbelow(W - int(st.rock.w)))
        if st.lives <= 0:
            st.game_over = True

    if st.player.intersects(st.diamond):
        st.diamonds += 1
        st.diamond.y = -50
        st.diamond.x = float(secrets.randbelow(W - int(st.diamond.w)))

    # seconds
    st.seconds = int(time.time() - st.started_at)


def _serialize(st: RoomState) -> dict:
    d = asdict(st)
    # dataclass->dict уже вложил Rect как dict
    return d


@app.websocket("/ws/game")
async def ws_game(ws: WebSocket, token: str, room: str = "default"):
    await ws.accept()
    username = TOKENS.get(token)
    if not username:
        await ws.send_json({"type": "state.error", "message": "unauthorized"})
        await ws.close()
        return

    st = ROOMS.get(room) or _reset_room(room)
    tick_rate = 30

    try:
        while True:
            # читаем ввод “пачкой”
            while True:
                try:
                    msg = await asyncio.wait_for(ws.receive_json(), timeout=0.001)
                    if msg.get("type") == "input.move":
                        st.move = msg.get("direction", "stop")
                    if msg.get("type") == "session.restart":
                        st = _reset_room(room)
                except TimeoutError:
                    break

            now = time.time()
            dt = max(0.0, min(0.05, now - st.last_tick))
            st.last_tick = now

            if not st.game_over:
                _step(st, dt)

            await ws.send_json({"type": "state.tick", "payload": _serialize(st)})
            if st.game_over:
                await ws.send_json({"type": "state.game_over", "payload": _serialize(st)})

            await asyncio.sleep(1 / tick_rate)
    except WebSocketDisconnect:
        return
```

---

## Запуск демо на уроке

1) Установить зависимости:

```bash
python -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn
```

2) Запуск:

```bash
uvicorn demo_backend:app --reload --port 8001
```

3) Проверка:

- `GET http://localhost:8001/health`
- `POST http://localhost:8001/auth/mock_login` body: `{"username":"egor"}`

---

## Как это объяснить (концептуально, коротко)

- **Клиент**: отправляет только “я нажал left/right/stop”.
- **Сервер**: на каждом тике пересчитывает физику/столкновения и отдает **состояние**.
- **Плюсы**: нельзя читерить “я собрал 999 алмазов”, потому что сервер считает сам.

---

## Упражнения (если останется время)

- Добавить `player_id` и 2 игрока в комнате.
- Добавить “онлайн” через `last_seen` и считать онлайн по комнатам.
- Добавить REST `GET /rooms` → показать сколько комнат и игроков.

