from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__, settings.log_dir, settings.log_level)

_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.db.dsn,
            poolclass=QueuePool,
            pool_size=settings.db.pool_min,
            max_overflow=settings.db.pool_max - settings.db.pool_min,
            pool_pre_ping=True,  # reconnect on stale connections
            pool_recycle=3600,   # recycle connections every hour
            echo=False,
        )
        logger.info(
            "Database engine created — host=%s db=%s",
            settings.db.host,
            settings.db.name,
        )
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionFactory


@contextmanager
def get_session() -> Generator[Session, None, None]:
    factory = get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def verify_connection() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection verified.")
        return True
    except Exception as exc:
        logger.error("Database connection failed: %s", exc)
        return False
