from pathlib import Path

import pytest
from sqlalchemy import inspect

from app.db import create_tables, database_url, get_session, make_engine

BACKEND_DIR = Path(__file__).resolve().parent.parent


def test_database_url_uses_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///somewhere/else.db")

    assert database_url() == "sqlite:///somewhere/else.db"


def test_database_url_defaults_to_sqlite_file_in_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    url = database_url()

    assert url.startswith("sqlite:///")
    db_file = Path(url.removeprefix("sqlite:///"))
    assert db_file.suffix == ".db"
    assert db_file.parent == BACKEND_DIR


def test_create_tables_creates_the_four_tables() -> None:
    engine = make_engine("sqlite://")

    create_tables(engine)

    assert set(inspect(engine).get_table_names()) == {
        "game",
        "question",
        "session",
        "answer",
    }


def test_get_session_yields_a_working_session() -> None:
    engine = make_engine("sqlite://")
    create_tables(engine)

    session = next(get_session(engine))

    assert session.bind is engine
