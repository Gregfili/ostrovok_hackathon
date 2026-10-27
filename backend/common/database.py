"""Движок SQLAlchemy и сессия для FastAPI. Файл базы тот же, что у sqlite3."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from common.snapshots import DATA
from common.tables import Base

BACKEND = Path(__file__).resolve().parents[1]
DB_PATH = DATA / "app.db"
DATABASE_URL = "sqlite:///" + DB_PATH.resolve().as_posix()

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30})
SessionLocal = sessionmaker(bind=engine, autoflush=True, autocommit=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def apply_migrations() -> None:
    """Пустая база получает таблицы из Alembic. Уже живая база отмечается текущей ревизией, недостающие таблицы досоздаются."""
    DATA.mkdir(parents=True, exist_ok=True)
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    existing = set(inspect(engine).get_table_names())
    if "alembic_version" in existing:
        command.upgrade(cfg, "head")
        return
    if existing:
        Base.metadata.create_all(engine)
        command.stamp(cfg, "head")
        return
    command.upgrade(cfg, "head")
