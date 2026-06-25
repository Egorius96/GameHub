"""Проверка сохранения алмазов в JSONB (in-place mutation не отслеживается SQLAlchemy)."""

from __future__ import annotations

from app.db.models import GameHubUser
from app.db.session import _session_factory
from app.integrations.users_api import attempt_insert_gamehub_user, users_api


def test_increment_diamonds_persists_to_db() -> None:
    uname = "_test_diamond_persist"
    db = _session_factory()()
    try:
        existing = db.query(GameHubUser).filter(GameHubUser.username == uname).first()
        if existing:
            db.delete(existing)
            db.commit()

        ok, _ = attempt_insert_gamehub_user(db, uname, "pass")
        assert ok
        db.commit()

        new_bal = users_api.increment_diamonds(uname, 3)
        assert new_bal == 3

        db.refresh(db.query(GameHubUser).filter(GameHubUser.username == uname).first())
        u = db.query(GameHubUser).filter(GameHubUser.username == uname).first()
        assert u is not None
        assert int((u.other_data or {}).get("diamonds", 0)) == 3
    finally:
        u = db.query(GameHubUser).filter(GameHubUser.username == uname).first()
        if u is not None:
            db.delete(u)
            db.commit()
        db.close()


if __name__ == "__main__":
    test_increment_diamonds_persists_to_db()
    print("ok")
