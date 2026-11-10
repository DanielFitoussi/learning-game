from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.db import create_tables


@pytest.fixture
def engine() -> Engine:
    """A fresh in-memory SQLite database with all tables.

    StaticPool keeps one connection, so every session sees the same database.
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    create_tables(engine)
    return engine


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """A session on the in-memory database."""
    with Session(engine) as session:
        yield session
