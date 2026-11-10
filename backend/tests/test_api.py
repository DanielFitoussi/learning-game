import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import openai
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, inspect
from sqlmodel import Session, select

from app.api import GENERATION_FAILED, app, get_db, get_engine, get_text_model
from app.generation import MAX_MATERIAL_CHARS, MAX_QUESTIONS
from app.models import Game
from app.storage import get_questions

# --- Helpers -------------------------------------------------------------------


class FakeTextModel:
    """Returns the next reply on each call, or raises it if it is an exception."""

    def __init__(self, *replies: str | Exception) -> None:
        self.replies = list(replies)
        self.calls = 0

    def complete_json(self, instructions: str, material: str) -> str:
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def question_dict(number: int) -> dict[str, Any]:
    return {
        "kind": "choose_one",
        "subject": "math",
        "chapter": "addition",
        "prompt": f"כמה זה {number} + 5?",
        "options": [
            {"text": str(number + 5), "is_correct": True},
            {"text": f"{number}5", "is_correct": False},
            {"text": str(number + 4), "is_correct": False},
        ],
    }


def questions_reply(count: int) -> str:
    return json.dumps({"questions": [question_dict(n) for n in range(1, count + 1)]})


def all_ok_review(count: int) -> str:
    reviews = [{"index": i, "ok": True, "problem": None} for i in range(count)]
    return json.dumps({"reviews": reviews})


def good_model(count: int) -> FakeTextModel:
    """A model that writes `count` valid questions and approves them all."""
    return FakeTextModel(questions_reply(count), all_ok_review(count))


BODY = {
    "subject": "math",
    "chapter": "addition",
    "grade": 2,
    "material": "When we add 7 and 5 we get 12.",
    "count": 3,
}


def saved_games(engine: Engine) -> int:
    with Session(engine) as session:
        return session.exec(select(func.count()).select_from(Game)).one()


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    """A client whose requests use the in-memory database.

    Not used as a context manager, so the real startup (which would create
    the database file) does not run.
    """

    def test_db() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = test_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def use_model(model: FakeTextModel) -> FakeTextModel:
    app.dependency_overrides[get_text_model] = lambda: model
    return model


# --- Creating a game -----------------------------------------------------------


def test_create_game_saves_game_and_questions(
    client: TestClient, engine: Engine
) -> None:
    use_model(good_model(3))

    response = client.post("/games", json=BODY)

    assert response.status_code == 201
    body = response.json()
    assert body["question_count"] == 3
    assert body["rejected"] == 0
    with Session(engine) as session:
        game = session.get(Game, body["game_id"])
        assert game is not None
        assert (game.subject, game.chapter, game.grade) == ("math", "addition", 2)
        prompts = [q.prompt for q in get_questions(session, body["game_id"])]
    assert prompts == ["כמה זה 1 + 5?", "כמה זה 2 + 5?", "כמה זה 3 + 5?"]


def test_create_game_reports_rejected_questions(client: TestClient) -> None:
    reply = json.loads(questions_reply(2))
    reply["questions"].append({"kind": "choose_one", "prompt": "broken"})
    use_model(FakeTextModel(json.dumps(reply), all_ok_review(2)))

    response = client.post("/games", json=BODY)

    assert response.status_code == 201
    assert response.json()["question_count"] == 2
    assert response.json()["rejected"] == 1


def test_count_defaults_to_5(client: TestClient) -> None:
    use_model(good_model(6))
    body = {key: value for key, value in BODY.items() if key != "count"}

    response = client.post("/games", json=body)

    assert response.status_code == 201
    assert response.json()["question_count"] == 5


# --- Bad input: 422 --------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"grade": 0}, "grade"),
        ({"grade": 4}, "grade"),
        ({"material": ""}, "material"),
        ({"material": "   "}, "material"),
        ({"material": "x" * (MAX_MATERIAL_CHARS + 1)}, "material"),
        ({"count": 0}, "count"),
        ({"count": MAX_QUESTIONS + 1}, "count"),
        ({"subject": ""}, "subject"),
    ],
)
def test_bad_input_gives_422_with_short_message(
    client: TestClient, engine: Engine, change: dict[str, Any], field: str
) -> None:
    model = use_model(good_model(3))

    response = client.post("/games", json=BODY | change)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, str)
    assert detail.startswith(f"{field}: ")
    assert len(detail) < 200  # the input is not echoed back
    assert model.calls == 0
    assert saved_games(engine) == 0


def test_missing_field_gives_422(client: TestClient) -> None:
    use_model(good_model(3))
    body = {key: value for key, value in BODY.items() if key != "subject"}

    response = client.post("/games", json=body)

    assert response.status_code == 422
    assert response.json()["detail"].startswith("subject: ")


# --- Generation failures: 502 ----------------------------------------------------


def assert_502_and_nothing_saved(response: Any, engine: Engine) -> None:
    assert response.status_code == 502
    assert response.json() == {"detail": GENERATION_FAILED}
    assert saved_games(engine) == 0


def test_generation_error_gives_502_and_saves_nothing(
    client: TestClient, engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    use_model(FakeTextModel("this is not json"))

    with caplog.at_level(logging.ERROR, logger="app.api"):
        response = client.post("/games", json=BODY)

    assert_502_and_nothing_saved(response, engine)
    assert "not valid JSON" in caplog.text  # the real reason is logged


def test_openai_error_gives_502_and_saves_nothing(
    client: TestClient, engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    use_model(FakeTextModel(openai.OpenAIError("rate limit reached")))

    with caplog.at_level(logging.ERROR, logger="app.api"):
        response = client.post("/games", json=BODY)

    assert_502_and_nothing_saved(response, engine)
    assert "rate limit reached" not in response.text
    assert "rate limit reached" in caplog.text


def test_missing_openai_model_gives_502(
    client: TestClient,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # No model override: the real get_text_model runs and fails before any
    # network call because OPENAI_MODEL is missing.
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    with caplog.at_level(logging.ERROR, logger="app.api"):
        response = client.post("/games", json=BODY)

    assert_502_and_nothing_saved(response, engine)
    assert "OPENAI_MODEL" not in response.text
    assert "OPENAI_MODEL" in caplog.text


# --- Startup ---------------------------------------------------------------------


def test_startup_creates_the_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "startup.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file.as_posix()}")
    get_engine.cache_clear()
    try:
        with TestClient(app):  # runs the startup code
            tables = set(inspect(get_engine()).get_table_names())
        get_engine().dispose()
    finally:
        get_engine.cache_clear()

    assert {"game", "question", "session", "answer"} <= tables
