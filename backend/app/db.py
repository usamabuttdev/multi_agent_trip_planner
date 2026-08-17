from __future__ import annotations

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import get_settings

log = logging.getLogger("trip.db")


class Base(DeclarativeBase):
    pass


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        return {
            "connect_args": {"check_same_thread": False},
            # Serverless: do not keep pooled connections across frozen invocations.
            "poolclass": NullPool,
        }
    return {"pool_pre_ping": True}


settings = get_settings()
engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

_schema_ready = False


def init_db() -> None:
    global _schema_ready
    from app.models import tables  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _schema_ready = True


def ensure_db() -> None:
    """Vercel's ASGI adapter often skips FastAPI lifespan, so tables may never exist."""
    global _schema_ready
    if _schema_ready:
        return
    init_db()


def db_ping() -> str | None:
    try:
        ensure_db()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return None
    except Exception as exc:  # noqa: BLE001
        log.exception("database ping failed")
        return f"{type(exc).__name__}: {exc}"


def get_session():
    ensure_db()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
