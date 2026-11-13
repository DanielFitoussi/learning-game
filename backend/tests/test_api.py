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
from app.models import Answer, Game, PlaySession
from app.questions import Question
from app.storage import get_questions, save_game

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
    "mode": "test",
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
        assert (game.subject, game.chapter, game.grade, game.mode) == (
            "math",
            "addition",
            2,
            "test",
        )
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


def test_create_game_saves_learning_mode(client: TestClient, engine: Engine) -> None:
    use_model(good_model(3))

    response = client.post("/games", json=BODY | {"mode": "learning"})

    assert response.status_code == 201
    with Session(engine) as session:
        game = session.get(Game, response.json()["game_id"])
    assert game is not None
    assert game.mode == "learning"


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
        ({"mode": "practice"}, "mode"),
        ({"mode": ""}, "mode"),
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


@pytest.mark.parametrize("field", ["subject", "mode"])
def test_missing_field_gives_422(
    client: TestClient, engine: Engine, field: str
) -> None:
    model = use_model(good_model(3))
    body = {key: value for key, value in BODY.items() if key != field}

    response = client.post("/games", json=body)

    assert response.status_code == 422
    assert response.json()["detail"].startswith(f"{field}: ")
    assert model.calls == 0
    assert saved_games(engine) == 0


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


# --- Playing a game --------------------------------------------------------------


def make_game(engine: Engine, count: int = 3, mode: str = "test") -> int:
    """Save a game straight to the database, without the model."""
    game_questions = [
        Question.model_validate(question_dict(n)) for n in range(1, count + 1)
    ]
    with Session(engine) as session:
        return save_game(session, "math", "addition", 2, mode, game_questions)


def question_ids(client: TestClient, game_id: int) -> list[int]:
    return [q["id"] for q in client.get(f"/games/{game_id}/questions").json()]


def new_session(client: TestClient, game_id: int) -> int:
    body = {"player_name": "Noa"}
    response = client.post(f"/games/{game_id}/sessions", json=body)
    assert response.status_code == 201
    return response.json()["session_id"]


def saved_answers(engine: Engine) -> list[Answer]:
    with Session(engine) as session:
        return list(session.exec(select(Answer)))


def answer(question_id: int, chosen_text: str, time_ms: int = 1200) -> dict[str, Any]:
    return {"question_id": question_id, "chosen_text": chosen_text, "time_ms": time_ms}


# GET /games/{game_id}


def test_get_game_returns_its_details_and_question_count(
    client: TestClient, engine: Engine
) -> None:
    game_id = make_game(engine, count=4, mode="learning")

    response = client.get(f"/games/{game_id}")

    assert response.status_code == 200
    assert response.json() == {
        "subject": "math",
        "chapter": "addition",
        "grade": 2,
        "mode": "learning",
        "question_count": 4,
    }


def test_get_unknown_game_is_404(client: TestClient) -> None:
    response = client.get("/games/999")

    assert response.status_code == 404
    assert "game 999" in response.json()["detail"]


# POST /games/{game_id}/sessions


def saved_session(engine: Engine, session_id: int) -> PlaySession:
    with Session(engine) as session:
        saved = session.get(PlaySession, session_id)
    assert saved is not None
    return saved


@pytest.mark.parametrize("mode", ["learning", "test"])
def test_start_session_returns_201_and_saves_trimmed_name_and_game_mode(
    client: TestClient, engine: Engine, mode: str
) -> None:
    game_id = make_game(engine, mode=mode)

    response = client.post(f"/games/{game_id}/sessions", json={"player_name": "  Noa "})

    assert response.status_code == 201
    saved = saved_session(engine, response.json()["session_id"])
    assert (saved.game_id, saved.player_name, saved.mode) == (game_id, "Noa", mode)


@pytest.mark.parametrize("sent_mode", ["learning", "practice"])
def test_start_session_ignores_mode_sent_by_the_client(
    client: TestClient, engine: Engine, sent_mode: str
) -> None:
    game_id = make_game(engine, mode="test")

    response = client.post(
        f"/games/{game_id}/sessions",
        json={"player_name": "Noa", "mode": sent_mode},
    )

    assert response.status_code == 201
    assert saved_session(engine, response.json()["session_id"]).mode == "test"


def test_start_session_accepts_a_40_character_name(
    client: TestClient, engine: Engine
) -> None:
    body = {"player_name": "a" * 40}
    response = client.post(f"/games/{make_game(engine)}/sessions", json=body)
    assert response.status_code == 201


def test_start_session_for_unknown_game_is_404(client: TestClient) -> None:
    body = {"player_name": "Noa"}
    response = client.post("/games/999/sessions", json=body)

    assert response.status_code == 404
    assert "game 999" in response.json()["detail"]


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"player_name": ""}, "player_name"),
        ({"player_name": "   "}, "player_name"),
        ({"player_name": "a" * 41}, "player_name"),
        ({}, "player_name"),
    ],
)
def test_start_session_rejects_bad_input(
    client: TestClient, engine: Engine, body: dict[str, Any], field: str
) -> None:
    response = client.post(f"/games/{make_game(engine)}/sessions", json=body)

    assert response.status_code == 422
    assert response.json()["detail"].startswith(f"{field}:")


# GET /games/{game_id}/questions


def test_get_questions_returns_option_texts_in_order(
    client: TestClient, engine: Engine
) -> None:
    game_id = make_game(engine, count=2)

    response = client.get(f"/games/{game_id}/questions")

    assert response.status_code == 200
    body = response.json()
    assert [q["prompt"] for q in body] == ["כמה זה 1 + 5?", "כמה זה 2 + 5?"]
    assert body[0]["options"] == ["6", "15", "5"]
    assert set(body[0]) == {"id", "prompt", "options"}


def test_get_questions_never_sends_is_correct(
    client: TestClient, engine: Engine
) -> None:
    response = client.get(f"/games/{make_game(engine)}/questions")

    assert response.status_code == 200
    assert "is_correct" not in response.text


def test_get_questions_of_unknown_game_is_404(client: TestClient) -> None:
    response = client.get("/games/999/questions")

    assert response.status_code == 404
    assert "game 999" in response.json()["detail"]


# POST /sessions/{session_id}/answers


def test_correct_answer_returns_201_and_is_correct_only(
    client: TestClient, engine: Engine
) -> None:
    game_id = make_game(engine)
    session_id = new_session(client, game_id)
    first = question_ids(client, game_id)[0]

    response = client.post(f"/sessions/{session_id}/answers", json=answer(first, "6"))

    assert response.status_code == 201
    assert response.json() == {"is_correct": True}
    [saved] = saved_answers(engine)
    assert (saved.session_id, saved.question_id, saved.time_ms) == (
        session_id,
        first,
        1200,
    )


def test_wrong_answer_does_not_reveal_the_correct_one(
    client: TestClient, engine: Engine
) -> None:
    game_id = make_game(engine)
    session_id = new_session(client, game_id)
    first = question_ids(client, game_id)[0]

    response = client.post(f"/sessions/{session_id}/answers", json=answer(first, "5"))

    assert response.status_code == 201
    assert response.json() == {"is_correct": False}


def test_second_answer_to_same_question_is_409_and_not_saved(
    client: TestClient, engine: Engine
) -> None:
    game_id = make_game(engine)
    session_id = new_session(client, game_id)
    first = question_ids(client, game_id)[0]
    url = f"/sessions/{session_id}/answers"

    client.post(url, json=answer(first, "6"))
    response = client.post(url, json=answer(first, "5"))

    assert response.status_code == 409
    assert "already answered" in response.json()["detail"]
    [saved] = saved_answers(engine)
    assert saved.chosen_text == "6"


def test_answer_for_unknown_session_is_404(client: TestClient, engine: Engine) -> None:
    first = question_ids(client, make_game(engine))[0]

    response = client.post("/sessions/999/answers", json=answer(first, "6"))

    assert response.status_code == 404
    assert "session 999" in response.json()["detail"]


def test_answer_for_unknown_question_is_404(client: TestClient, engine: Engine) -> None:
    session_id = new_session(client, make_game(engine))

    response = client.post(f"/sessions/{session_id}/answers", json=answer(999, "6"))

    assert response.status_code == 404
    assert "question 999" in response.json()["detail"]


def test_answer_with_question_from_another_game_is_422(
    client: TestClient, engine: Engine
) -> None:
    session_id = new_session(client, make_game(engine))
    other_question = question_ids(client, make_game(engine))[0]

    response = client.post(
        f"/sessions/{session_id}/answers", json=answer(other_question, "6")
    )

    assert response.status_code == 422
    assert "not part of" in response.json()["detail"]
    assert saved_answers(engine) == []


def test_answer_that_is_not_an_option_is_422(
    client: TestClient, engine: Engine
) -> None:
    game_id = make_game(engine)
    session_id = new_session(client, game_id)
    first = question_ids(client, game_id)[0]

    response = client.post(f"/sessions/{session_id}/answers", json=answer(first, "99"))

    assert response.status_code == 422
    assert "not one of" in response.json()["detail"]
    assert saved_answers(engine) == []


def test_answer_with_negative_time_is_422(client: TestClient, engine: Engine) -> None:
    game_id = make_game(engine)
    session_id = new_session(client, game_id)
    first = question_ids(client, game_id)[0]

    response = client.post(
        f"/sessions/{session_id}/answers", json=answer(first, "6", time_ms=-1)
    )

    assert response.status_code == 422
    assert response.json()["detail"].startswith("time_ms:")
    assert saved_answers(engine) == []
