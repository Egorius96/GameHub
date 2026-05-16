from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.models import GameHubUser
from app.db.session import engine, _session_factory


def ensure_catalog_user() -> None:
    """
    Для внутренних задач (tamagochi world refresh, leaderboard) нужен сервисный пользователь каталога.
    Раньше он жил во внешнем Users API; теперь создаём/поддерживаем его локально.
    """
    db = _session_factory()()
    try:
        u = db.query(GameHubUser).filter(GameHubUser.username == settings.catalog_username).first()
        if u is None:
            u = GameHubUser(
                username=settings.catalog_username,
                password=settings.catalog_password,
                project=settings.project_name,
                other_data={},
            )
            db.add(u)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
        else:
            # поддерживаем пароль/проект актуальными
            changed = False
            if u.password != settings.catalog_password:
                u.password = settings.catalog_password
                changed = True
            if u.project != settings.project_name:
                u.project = settings.project_name
                changed = True
            if changed:
                db.commit()
    finally:
        db.close()

