"""Database tables: games, their questions, play sessions and answers."""

from datetime import UTC, datetime
from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel


def utc_now() -> datetime:
    """The current time in UTC."""
    return datetime.now(UTC)


class Game(SQLModel, table=True):
    """A generated game for one chapter of one subject."""

    id: int | None = Field(default=None, primary_key=True)
    subject: str
    chapter: str
    grade: int
    created_at: datetime = Field(default_factory=utc_now)


class Question(SQLModel, table=True):
    """One question in a game. `position` is its order in the game, from 0."""

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id", index=True)
    position: int
    prompt: str
    options: list[dict[str, Any]] = Field(sa_column=Column(JSON, nullable=False))
    """A list of {"text": str, "is_correct": bool}."""


class PlaySession(SQLModel, table=True):
    """One child playing one game.

    Named PlaySession so it does not clash with SQLModel's database Session.
    """

    __tablename__ = "session"

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id", index=True)
    player_name: str
    mode: str
    """"learning" or "test"."""
    started_at: datetime = Field(default_factory=utc_now)


class Answer(SQLModel, table=True):
    """One answer a child gave to one question during a session."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    question_id: int = Field(foreign_key="question.id", index=True)
    chosen_text: str
    is_correct: bool
    time_ms: int
    answered_at: datetime = Field(default_factory=utc_now)
