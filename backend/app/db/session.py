from __future__ import annotations

import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def _db_url() -> str:
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "gamehub")
    user = os.getenv("DB_USER", "gamehub")
    password = os.getenv("DB_PASSWORD", "gamehub")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


@lru_cache
def engine():
    return create_engine(_db_url(), pool_pre_ping=True)


@lru_cache
def _session_factory():
    return sessionmaker(bind=engine(), autocommit=False, autoflush=False)


def get_db() -> Session:
    db = _session_factory()()
    try:
        yield db
    finally:
        db.close()

