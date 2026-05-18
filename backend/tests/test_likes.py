from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.likes import _my_vote_today, _total_like_counts
from app.db.models import GameLike


def _session():
    engine = create_engine("sqlite:///:memory:")
    GameLike.__table__.create(engine, checkfirst=True)
    return sessionmaker(bind=engine)()


def test_total_like_counts_sums_all_days() -> None:
    db = _session()
    yesterday = date.today() - timedelta(days=1)
    db.add(GameLike(user_id=1, username="alice", game_key="rps_game", day=yesterday, ip="1.2.3.4"))
    db.add(GameLike(user_id=1, username="alice", game_key="misha_pro_racing_game", day=date.today(), ip="1.2.3.4"))
    db.commit()

    counts = _total_like_counts(db)
    assert counts["rps_game"] == 1
    assert counts["misha_pro_racing_game"] == 1


def test_my_vote_today_only_current_day() -> None:
    db = _session()
    yesterday = date.today() - timedelta(days=1)
    db.add(GameLike(user_id=2, username="bob", game_key="rps_game", day=yesterday, ip="1.2.3.4"))
    db.commit()

    assert _my_vote_today(db, 2, date.today()) is None
    assert _my_vote_today(db, 2, yesterday) == "rps_game"
