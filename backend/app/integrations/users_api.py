from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.reserved_usernames import is_reserved_username
from app.db.models import GameHubUser, WarningHistory
from app.db.session import _session_factory
from app.services.ban_state import clear_expired_temp_ban, is_login_blocked, temp_ban_remaining_seconds, utcnow


def _sync_session_diamonds(username: str, balance: int) -> None:
    """Подтянуть баланс алмазов в активных JWT-сессиях после изменения в БД."""
    from app.core.gameshub import ensure_gameshub_schema
    from app.core.session import sessions

    for sess in sessions.values():
        if sess.username == username:
            o = ensure_gameshub_schema(sess.user.setdefault("other_data", {}) or {})
            o["diamonds"] = balance
            sess.user["other_data"] = o


def default_gamehub_other_data() -> dict[str, Any]:
    """Начальный other_data для нового GameHub-пользователя (как при register)."""
    game_key = settings.pro_racing_game_key
    rps_key = settings.rps_game_key
    tamagochi_key = settings.tamagochi_game_key
    tt_key = settings.team_territory_game_key
    mc2d_key = settings.minecraft_2d_online_game_key
    return {
        "diamonds": 0,
        "games": {
            game_key: {
                "car_level": 1,
                "two_players_gamemode": False,
                "matches_count": 0,
                "high_score_seconds": 0,
                "superpowers": {
                    "drugs": False,
                    "immue": False,
                    "time_stop": False,
                    "minigun": False,
                    "rockspeed": False,
                    "hearty_rock": False,
                },
                "playtime": 0,
            },
            rps_key: {"playtime": 0},
            tamagochi_key: {
                "playtime": 0,
                "pet": None,
                "pet_state": None,
                "last_update_at": None,
                "neglect": {},
                "coins": 0,
                "inventory": {
                    "food_by_type": {"cat": 0, "dog": 0, "pokemon": 0, "capybara": 0, "alien": 0},
                    "toy": 0,
                },
                "shop": {},
            },
            tt_key: {"playtime": 0, "match_rewards": {}},
            mc2d_key: {
                "playtime": 0,
                "diamond_dust": 0,
                "dust_exchange_rate": 14,
                "dust_rate_history": [],
                "exchange_idempotency": {},
                "deliver_idempotency": {},
            },
        },
    }


def attempt_insert_gamehub_user(db: Session, username: str, password: str) -> tuple[bool, GameHubUser | None]:
    """Создать пользователя в текущей сессии (savepoint). False — ник уже занят."""
    if is_reserved_username(username):
        return False, None
    try:
        with db.begin_nested():
            u = GameHubUser(
                username=username,
                password=password,
                project=settings.project_name,
                other_data=default_gamehub_other_data(),
            )
            db.add(u)
            db.flush()
    except IntegrityError:
        return False, None
    u = db.query(GameHubUser).filter(GameHubUser.username == username).first()
    return True, u


class UsersApiClient:
    """
    Встроенный Users API для GameHub (замена отдельного сервиса).

    Интерфейс сохранён максимально близко к прежнему, чтобы не переписывать весь backend.
    """

    def _db(self) -> Session:
        return _session_factory()()

    @staticmethod
    def _user_dict(u: GameHubUser) -> dict[str, Any]:
        return {
            "username": u.username,
            "password": u.password,
            "project": u.project,
            "other_data": u.other_data or {},
        }

    def auth(self, username: str, password: str) -> dict:
        db = self._db()
        try:
            u = (
                db.query(GameHubUser)
                .filter(GameHubUser.username == username)
                .filter(GameHubUser.password == password)
                .first()
            )
            if u is None:
                return {}
            clear_expired_temp_ban(db, u)
            db.refresh(u)
            if is_login_blocked(u):
                bu = getattr(u, "banned_until", None)
                if bu is not None:
                    return {
                        "error": "temp_ban",
                        "banned_until": bu.isoformat(),
                        "seconds_remaining": temp_ban_remaining_seconds(u),
                    }
                rows = (
                    db.query(WarningHistory)
                    .filter(WarningHistory.user_id == u.id)
                    .order_by(WarningHistory.created_at.desc())
                    .limit(100)
                    .all()
                )
                hist = [{"text": rw.text, "created_at": rw.created_at.isoformat()} for rw in rows]
                return {"error": "blocked", "warnings_history": hist}
            return self._user_dict(u)
        finally:
            db.close()

    def register(self, username: str, password: str) -> dict:
        db = self._db()
        try:
            ok, u = attempt_insert_gamehub_user(db, username.strip(), password)
            if not ok or u is None:
                db.rollback()
                return {"detail": "Username already exists"}
            db.commit()
            db.refresh(u)
            return self._user_dict(u)
        except Exception:
            db.rollback()
            return {"detail": "Username already exists"}
        finally:
            db.close()

    def create_user(self, username: str, password: str, other_data: dict) -> dict:
        db = self._db()
        try:
            u = GameHubUser(
                username=username,
                password=password,
                project=settings.project_name,
                other_data=other_data,
            )
            db.add(u)
            db.commit()
            db.refresh(u)
            return self._user_dict(u)
        except IntegrityError:
            db.rollback()
            return {"detail": "Username already exists"}
        finally:
            db.close()

    def increment_diamonds(self, username: str, delta: int = 1) -> int | None:
        """Увеличить алмазы в БД по логину; вернуть новый баланс или None."""
        from app.core.gameshub import ensure_gameshub_schema

        db = self._db()
        try:
            u = db.query(GameHubUser).filter(GameHubUser.username == username).first()
            if u is None:
                return None
            other = ensure_gameshub_schema(u.other_data or {})
            new_val = int(other.get("diamonds", 0)) + int(delta)
            other["diamonds"] = new_val
            u.other_data = other
            db.commit()
            _sync_session_diamonds(username, new_val)
            return new_val
        except Exception:
            db.rollback()
            return None
        finally:
            db.close()

    def get_diamond_balance(self, username: str) -> int | None:
        """Текущий баланс алмазов из БД или None, если пользователь не найден."""
        from app.core.gameshub import ensure_gameshub_schema

        db = self._db()
        try:
            u = db.query(GameHubUser).filter(GameHubUser.username == username).first()
            if u is None:
                return None
            other = ensure_gameshub_schema(u.other_data or {})
            return int(other.get("diamonds", 0))
        finally:
            db.close()

    def adjust_diamonds(self, username: str, delta: int) -> int | None:
        """Изменить баланс алмазов (delta может быть отрицательным). None — пользователь не найден или недостаточно средств."""
        from app.core.gameshub import ensure_gameshub_schema

        db = self._db()
        try:
            u = db.query(GameHubUser).filter(GameHubUser.username == username).first()
            if u is None:
                return None
            other = ensure_gameshub_schema(u.other_data or {})
            cur = int(other.get("diamonds", 0))
            new_val = cur + int(delta)
            if new_val < 0:
                return None
            other["diamonds"] = new_val
            u.other_data = other
            db.commit()
            _sync_session_diamonds(username, new_val)
            return new_val
        except Exception:
            db.rollback()
            return None
        finally:
            db.close()

    def patch_game_data(self, username: str, game_key: str, mutator: Callable[[dict], None]) -> dict[str, Any] | None:
        """Обновить other_data.games[game_key] через mutator (изменяет dict на месте)."""
        from app.core.gameshub import ensure_gameshub_schema

        db = self._db()
        try:
            u = db.query(GameHubUser).filter(GameHubUser.username == username).first()
            if u is None:
                return None
            other = ensure_gameshub_schema(u.other_data or {})
            games = other.get("games")
            if not isinstance(games, dict):
                games = {}
                other["games"] = games
            g = games.get(game_key)
            if not isinstance(g, dict):
                g = {}
            mutator(g)
            games[game_key] = g
            u.other_data = other
            db.commit()
            return dict(g)
        except Exception:
            db.rollback()
            return None
        finally:
            db.close()

    def mc2d_exchange_diamond_for_dust(self, username: str, idempotency_key: str) -> dict[str, Any]:
        """
        Списать 1 алмаз GameHub, начислить пыль по текущему курсу (§13.4).
        Идемпотентность по ключу в games[minecraft_2d_online].exchange_idempotency.
        """
        from app.core.gameshub import ensure_gameshub_schema

        idem = (idempotency_key or "").strip()[:128]
        if not idem:
            return {"ok": False, "error": "idempotency_required"}
        gk = settings.minecraft_2d_online_game_key
        db = self._db()
        try:
            u = db.query(GameHubUser).filter(GameHubUser.username == username).with_for_update().first()
            if u is None:
                return {"ok": False, "error": "user"}
            other = ensure_gameshub_schema(u.other_data or {})
            games = other.setdefault("games", {})
            if not isinstance(games, dict):
                games = {}
                other["games"] = games
            g = games.get(gk)
            if not isinstance(g, dict):
                g = {}
            ex = g.get("exchange_idempotency")
            if not isinstance(ex, dict):
                ex = {}
            if idem in ex:
                cached = ex[idem]
                dust = int(g.get("diamond_dust", 0))
                rate_val = int(g.get("dust_exchange_rate", 14))
                if isinstance(cached, dict):
                    dust = int(cached.get("dust", dust))
                    rate_val = int(cached.get("rate", rate_val))
                db.commit()
                return {
                    "ok": True,
                    "cached": True,
                    "dust": dust,
                    "gained": 0,
                    "rate": rate_val,
                    "diamonds": int(other.get("diamonds", 0)),
                }
            cur_d = int(other.get("diamonds", 0))
            if cur_d < 1:
                db.rollback()
                return {"ok": False, "error": "not_enough_diamonds"}
            rate = int(g.get("dust_exchange_rate", 14))
            rate = max(8, min(20, rate))
            cur_dust = int(g.get("diamond_dust", 0))
            new_dust = cur_dust + rate
            other["diamonds"] = cur_d - 1
            g["diamond_dust"] = new_dust
            ex[idem] = {"dust": new_dust, "rate": rate}
            keys = list(ex.keys())[-100:]
            g["exchange_idempotency"] = {k: ex[k] for k in keys}
            games[gk] = g
            u.other_data = other
            db.commit()
            _sync_session_diamonds(username, int(other["diamonds"]))
            return {
                "ok": True,
                "cached": False,
                "dust": new_dust,
                "gained": rate,
                "rate": rate,
                "diamonds": int(other["diamonds"]),
            }
        except Exception:
            db.rollback()
            return {"ok": False, "error": "server"}
        finally:
            db.close()

    def adjust_diamonds_session(self, db: Session, username: str, delta: int) -> int | None:
        """То же, но на переданной сессии (только flush, без commit) — caller делает commit и sync сессий."""
        from app.core.gameshub import ensure_gameshub_schema

        u = db.query(GameHubUser).filter(GameHubUser.username == username).with_for_update().first()
        if u is None:
            return None
        other = ensure_gameshub_schema(u.other_data or {})
        cur = int(other.get("diamonds", 0))
        new_val = cur + int(delta)
        if new_val < 0:
            return None
        other["diamonds"] = new_val
        u.other_data = other
        db.flush()
        return new_val

    def save_user(self, user: dict) -> bool:
        db = self._db()
        try:
            username = str(user.get("username") or "")
            password = str(user.get("password") or "")
            other = user.get("other_data") if isinstance(user.get("other_data"), dict) else {}
            u = db.query(GameHubUser).filter(GameHubUser.username == username).first()
            if u is None:
                return False
            # password is mutable (legacy behavior)
            u.password = password or u.password
            u.other_data = other
            u.project = settings.project_name
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    def fetch_project_users_list(self, username: str, password: str) -> tuple[bool, list[Any]]:
        db = self._db()
        try:
            auth_u = (
                db.query(GameHubUser)
                .filter(GameHubUser.username == username)
                .filter(GameHubUser.password == password)
                .first()
            )
            if auth_u is None:
                return True, []
            users = db.query(GameHubUser).filter(GameHubUser.project == auth_u.project).all()
            return True, [{"username": u.username, "other_data": u.other_data or {}} for u in users]
        except Exception:
            return False, []
        finally:
            db.close()

    def get_users_by_project(self, username: str, password: str) -> dict:
        ok, users = self.fetch_project_users_list(username, password)
        return {"users": users if ok else []}

    def delete_user(self, username: str, password: str) -> tuple[int, dict[str, Any]]:
        # Совместимость со старым сервисом: при любой ошибке возвращал 500.
        db = self._db()
        try:
            u = (
                db.query(GameHubUser)
                .filter(GameHubUser.username == username)
                .filter(GameHubUser.password == password)
                .first()
            )
            if u is None:
                return 500, {"detail": "Failed to delete user"}
            db.delete(u)
            db.commit()
            return 200, {"message": "User deleted successfully"}
        except Exception:
            db.rollback()
            return 500, {"detail": "Failed to delete user"}
        finally:
            db.close()


users_api = UsersApiClient()


def sync_diamonds_to_sessions(username: str, balance: int) -> None:
    _sync_session_diamonds(username, balance)
