from __future__ import annotations

import random
import time

from app.games.pro_racing.models import Entity, GameState, PlayerState

CAR_SPEED = {1: 3, 2: 6, 3: 10}
# Спрайты на клиенте: машина 150×68, камень 100×80; коллизия — меньше, по центру.
CAR_SPRITE_W, CAR_SPRITE_H = 150.0, 68.0
CAR_HIT_W, CAR_HIT_H = 120.0, 50.0
CAR_HIT_OX = (CAR_SPRITE_W - CAR_HIT_W) / 2.0
CAR_HIT_OY = (CAR_SPRITE_H - CAR_HIT_H) / 2.0
ROCK_SPRITE_W, ROCK_SPRITE_H = 100.0, 80.0
ROCK_HIT_W, ROCK_HIT_H = 70.0, 60.0
ROCK_HIT_OX = (ROCK_SPRITE_W - ROCK_HIT_W) / 2.0
ROCK_HIT_OY = (ROCK_SPRITE_H - ROCK_HIT_H) / 2.0
# Базовая вероятность как в pygame 0.004; на 20% реже для веб-версии
DIAMOND_SPAWN_CHANCE = 0.004 * 0.8
# Ускорение камней (+0.1/с в оригинале) ×1.5 для веб-версии
ROCK_ACCEL_PER_SEC = 0.15
ROCK_ACCEL_ACS_PER_SEC = 0.45
HARD_MODIFIERS = [
    "rockhit_2",
    "diamond_no",
    "start_1hp",
    "no_super",
    "rocks_sec",
    "rocks_acs",
    "big_car",
    "inverted_move",
    "low_diam",
]


def intersects(ax: float, ay: float, aw: float, ah: float, bx: float, by: float, bw: float, bh: float) -> bool:
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def car_hit_rect(player: PlayerState) -> tuple[float, float, float, float]:
    return player.x + CAR_HIT_OX, player.y + CAR_HIT_OY, CAR_HIT_W, CAR_HIT_H


def rock_hit_rect(rock: Entity) -> tuple[float, float, float, float]:
    return rock.x + ROCK_HIT_OX, rock.y + ROCK_HIT_OY, ROCK_HIT_W, ROCK_HIT_H


def rects_intersect_car_rock(player: PlayerState, rock: Entity) -> bool:
    ax, ay, aw, ah = car_hit_rect(player)
    bx, by, bw, bh = rock_hit_rect(rock)
    return intersects(ax, ay, aw, ah, bx, by, bw, bh)


class GameEngine:
    def __init__(self, mode: str, car_level: int) -> None:
        self.state = GameState(mode=mode)
        self.car_level = max(1, min(3, car_level))
        if mode == "pvp_local":
            self.state.player1.y = 100
            self.state.player2.y = 450
            self.state.rock1.y = random.randint(0, 250)
            self.state.rock2.y = random.randint(300, 650)
        if mode == "hard":
            self.state.hard_modifier = random.choice(HARD_MODIFIERS)
            if self.state.hard_modifier == "start_1hp":
                self.state.player1.lives = 1

    def input_move(
        self,
        player: int,
        direction: str | None = None,
        *,
        dx: int | None = None,
        dy: int | None = None,
    ) -> None:
        pl = self.state.player1 if player == 1 else self.state.player2
        if dx is not None or dy is not None:
            pl.move_x = max(-1, min(1, int(dx or 0)))
            pl.move_y = max(-1, min(1, int(dy or 0)))
            pl.direction = "stop"  # type: ignore[assignment]
            if pl.move_y < 0:
                pl.direction = "up"  # type: ignore[assignment]
            elif pl.move_y > 0:
                pl.direction = "down"  # type: ignore[assignment]
            elif pl.move_x < 0:
                pl.direction = "left"  # type: ignore[assignment]
            elif pl.move_x > 0:
                pl.direction = "right"  # type: ignore[assignment]
            return
        d = str(direction or "stop")
        pl.direction = d  # type: ignore[assignment]
        pl.move_x = 0
        pl.move_y = 0
        if d == "up":
            pl.move_y = -1
        elif d == "down":
            pl.move_y = 1
        elif d == "left":
            pl.move_x = -1
        elif d == "right":
            pl.move_x = 1

    def ability(self, name: str) -> None:
        now = time.time()
        if name == "drugs" and self.state.drugs_limit > 0 and self.state.player1.lives > 1:
            self.state.drugs_limit -= 1
            self.state.player1.lives -= 1
            self.state.seconds += 10
        elif name == "rockspeed" and self.state.rockspeed_limit > 0:
            self.state.rockspeed_limit -= 1
            self.state.speed_rock = 10.0
        elif name == "immue":
            self.state.immue_until = now + 10
        elif name == "hearty_rock":
            self.state.hearty_ready = True

    def _move_player(self, player, top_limit: int, bottom_limit: int) -> None:
        dx = int(player.move_x)
        dy = int(player.move_y)
        if dx == 0 and dy == 0:
            return
        v_speed = float(CAR_SPEED[self.car_level])
        h_speed = 5.0
        if dx != 0 and dy != 0:
            k = 0.7071067811865476
            v_step = v_speed * k
            h_step = h_speed * k
        else:
            v_step = v_speed if dy != 0 else 0.0
            h_step = h_speed if dx != 0 else 0.0
        if dy < 0 and player.y > top_limit:
            player.y -= v_step
        elif dy > 0 and player.y < bottom_limit:
            player.y += v_step
        if dx < 0 and player.x > 0:
            player.x -= h_step
        elif dx > 0 and player.x < 1050:
            player.x += h_step

    def _spawn_diamond(self) -> None:
        if self.state.diamond_cd > 0:
            self.state.diamond_cd -= 1
            return
        if self.state.diamond.x < -100 and random.random() < DIAMOND_SPAWN_CHANCE:
            self.state.diamond.x = random.randint(1200, 1600)
            self.state.diamond.y = random.randint(0, 650)

    def tick(self) -> dict:
        if self.state.game_over:
            return self.serialize()

        self.state.frame += 1
        if self.state.frame >= 30:
            self.state.frame = 0
            self.state.seconds += 1
            self.state.speed_rock += (
                ROCK_ACCEL_ACS_PER_SEC
                if self.state.hard_modifier == "rocks_acs"
                else ROCK_ACCEL_PER_SEC
            )

        if self.state.mode == "pvp_local":
            self._move_player(self.state.player1, 0, 260)
            self._move_player(self.state.player2, 360, 630)
        else:
            self._move_player(self.state.player1, 0, 635)

        self.state.rock1.x -= self.state.speed_rock
        self.state.rock2.x -= self.state.speed_rock
        if self.state.rock1.x < -100:
            self.state.rock1.x = random.randint(1200, 1600)
            self.state.rock1.y = random.randint(0, 250 if self.state.mode == "pvp_local" else 650)
        if self.state.rock2.x < -100:
            self.state.rock2.x = random.randint(1200, 1600)
            self.state.rock2.y = random.randint(300, 650) if self.state.mode == "pvp_local" else random.randint(0, 650)

        self._spawn_diamond()
        if self.state.diamond.x > -100:
            self.state.diamond.x -= 25

        self._resolve_collisions()
        return self.serialize()

    def _resolve_collisions(self) -> None:
        p1 = self.state.player1
        p2 = self.state.player2
        now = time.time()

        def hit(player, rock) -> None:
            if now < self.state.immue_until:
                return
            if self.state.hearty_ready:
                player.lives += 1
                self.state.hearty_ready = False
                return
            if self.state.hard_modifier == "rockhit_2":
                player.lives -= 2
            else:
                player.lives -= 1
            if self.state.hard_modifier == "rocks_sec":
                self.state.seconds = max(0, self.state.seconds - 10)

        if rects_intersect_car_rock(p1, self.state.rock1):
            hit(p1, self.state.rock1)
            self.state.rock1.x = random.randint(1200, 1600)
        if rects_intersect_car_rock(p1, self.state.rock2):
            hit(p1, self.state.rock2)
            self.state.rock2.x = random.randint(1200, 1600)

        if self.state.mode == "pvp_local":
            if rects_intersect_car_rock(p2, self.state.rock1):
                p2.lives -= 1
                self.state.rock1.x = random.randint(1200, 1600)
            if rects_intersect_car_rock(p2, self.state.rock2):
                p2.lives -= 1
                self.state.rock2.x = random.randint(1200, 1600)

        cx, cy, cw, ch = car_hit_rect(p1)
        if self.state.diamond.x > -100 and intersects(cx, cy, cw, ch, self.state.diamond.x, self.state.diamond.y, 100, 60):
            if self.state.hard_modifier != "diamond_no":
                p1.lives += 2 if self.state.hard_modifier == "low_diam" else 1
            self.state.diamonds_collected += 1 if self.state.mode != "hard" else 2
            self.state.diamond.x = -200
            self.state.diamond_cd = 180

        if self.state.mode == "pvp_local" and self.state.diamond.x > -100:
            cx2, cy2, cw2, ch2 = car_hit_rect(p2)
            if intersects(cx2, cy2, cw2, ch2, self.state.diamond.x, self.state.diamond.y, 100, 60):
                p2.lives += 1
                self.state.diamond.x = -200
                self.state.diamond_cd = 180

        if self.state.mode == "pvp_local":
            if p1.lives < 1 or p2.lives < 1:
                self.state.game_over = True
                if p1.lives < 1 and p2.lives >= 1:
                    self.state.winner = "P2"
                elif p2.lives < 1 and p1.lives >= 1:
                    self.state.winner = "P1"
                else:
                    self.state.winner = "DRAW"
        else:
            if p1.lives < 1:
                self.state.game_over = True

    def serialize(self) -> dict:
        return {
            "mode": self.state.mode,
            "seconds": self.state.seconds,
            "speed_rock": self.state.speed_rock,
            "player1": vars(self.state.player1),
            "player2": vars(self.state.player2),
            "rock1": vars(self.state.rock1),
            "rock2": vars(self.state.rock2),
            "diamond": vars(self.state.diamond),
            "diamond_cd": self.state.diamond_cd,
            "game_over": self.state.game_over,
            "persisted": self.state.persisted,
            "winner": self.state.winner,
            "hard_modifier": self.state.hard_modifier,
            "diamonds_collected": self.state.diamonds_collected,
            "drugs_limit": self.state.drugs_limit,
            "rockspeed_limit": self.state.rockspeed_limit,
            "immue_left": max(0, int(self.state.immue_until - time.time())),
            "hearty_ready": self.state.hearty_ready,
        }
