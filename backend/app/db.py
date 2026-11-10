"""Database connection: where the database is, creating tables, opening sessions."""

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  (registers the tables on SQLModel.metadata)

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_FILE = BACKEND_DIR / "learning_quest.db"


def database_url() -> str:
    """The DATABASE_URL environment variable, or a local SQLite file in backend/."""
    return os.environ.get("DATABASE_URL") or f"sqlite:///{DEFAULT_DB_FILE.as_posix()}"


def make_engine(url: str) -> Engine:
    """Create an engine for the given database URL."""
    return create_engine(url)


def create_tables(engine: Engine) -> None:
    """Create all tables that do not exist yet."""
    SQLModel.metadata.create_all(engine)


def get_session(engine: Engine) -> Iterator[Session]:
    """Yield a database session and close it afterwards."""
    with Session(engine) as session:
        yield session
