import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app import questions, storage
from app.errors import DuplicateAnswerError, NotFoundError
from app.models import Answer, PlaySession
from app.storage import get_questions, save_answer, save_game, start_session


def make_question(prompt: str, correct: str, wrong: list[str]) -> questions.Question:
    options = [questions.AnswerOption(text=correct, is_correct=True)]
    options += [questions.AnswerOption(text=text, is_correct=False) for text in wrong]
    return questions.Question(
        kind="choose_one",
        subject="math",
        chapter="addition",
        prompt=prompt,
        options=options,
    )


QUESTIONS = [
    make_question("7 + 5 = ?", "12", ["11", "13"]),
    make_question("3 + 4 = ?", "7", ["6", "8"]),
    make_question("Past of go?", "went", ["goed", "go"]),
]


def new_game(db: Session) -> int:
    return save_game(db, "math", "addition", 2, QUESTIONS)


# --- save_game / get_questions ---


def test_save_game_keeps_questions_in_order_with_options(db: Session) -> None:
    game_id = new_game(db)

    saved = get_questions(db, game_id)

    assert [q.prompt for q in saved] == ["7 + 5 = ?", "3 + 4 = ?", "Past of go?"]
    assert [q.position for q in saved] == [0, 1, 2]
    assert saved[0].options == [
        {"text": "12", "is_correct": True},
        {"text": "11", "is_correct": False},
        {"text": "13", "is_correct": False},
    ]


def test_get_questions_returns_only_that_games_questions(db: Session) -> None:
    first = new_game(db)
    second = save_game(db, "english", "past tense", 3, [QUESTIONS[2]])

    assert len(get_questions(db, first)) == 3
    assert [q.prompt for q in get_questions(db, second)] == ["Past of go?"]


def test_get_questions_of_unknown_game_is_not_found(db: Session) -> None:
    with pytest.raises(NotFoundError, match="game"):
        get_questions(db, 999)


@pytest.mark.parametrize("grade", [0, 4])
def test_save_game_rejects_grade_outside_1_to_3(db: Session, grade: int) -> None:
    with pytest.raises(ValueError, match="grade"):
        save_game(db, "math", "addition", grade, QUESTIONS)


# --- start_session ---


def test_start_session_returns_new_ids(db: Session) -> None:
    game_id = new_game(db)

    first = start_session(db, game_id, "Noa", "learning")
    second = start_session(db, game_id, "Ari", "test")

    assert first != second


def test_start_session_rejects_unknown_game(db: Session) -> None:
    with pytest.raises(NotFoundError, match="does not exist"):
        start_session(db, 999, "Noa", "learning")


def test_start_session_rejects_unknown_mode(db: Session) -> None:
    with pytest.raises(ValueError, match="mode"):
        start_session(db, new_game(db), "Noa", "practice")


def test_start_session_rejects_empty_name(db: Session) -> None:
    with pytest.raises(ValueError, match="player_name"):
        start_session(db, new_game(db), "   ", "learning")


# --- save_answer ---


@pytest.fixture
def played(db: Session) -> tuple[int, list[int]]:
    """A started session and the ids of its game's questions."""
    game_id = new_game(db)
    session_id = start_session(db, game_id, "Noa", "test")
    return session_id, [q.id for q in get_questions(db, game_id)]


def saved_answers(db: Session) -> list[Answer]:
    return list(db.exec(select(Answer)))


def test_save_answer_marks_correct_answer(
    db: Session, played: tuple[int, list[int]]
) -> None:
    session_id, question_ids = played

    assert save_answer(db, session_id, question_ids[0], "12", 1500) is True

    [answer] = saved_answers(db)
    assert answer.is_correct is True
    assert (answer.session_id, answer.question_id) == (session_id, question_ids[0])
    assert (answer.chosen_text, answer.time_ms) == ("12", 1500)


def test_save_answer_marks_wrong_answer(
    db: Session, played: tuple[int, list[int]]
) -> None:
    session_id, question_ids = played

    assert save_answer(db, session_id, question_ids[2], "goed", 800) is False

    [answer] = saved_answers(db)
    assert answer.is_correct is False
    assert answer.chosen_text == "goed"


def test_save_answer_ignores_case_and_spaces(
    db: Session, played: tuple[int, list[int]]
) -> None:
    session_id, question_ids = played

    assert save_answer(db, session_id, question_ids[2], "  WENT ", 900) is True
    assert saved_answers(db)[0].chosen_text == "went"


def test_save_answer_rejects_text_that_is_not_an_option(
    db: Session, played: tuple[int, list[int]]
) -> None:
    session_id, question_ids = played

    with pytest.raises(ValueError, match="not one of"):
        save_answer(db, session_id, question_ids[0], "99", 1000)
    assert saved_answers(db) == []


def test_save_answer_rejects_question_from_another_game(
    db: Session, played: tuple[int, list[int]]
) -> None:
    session_id, _ = played
    other_game = save_game(db, "english", "past tense", 1, [QUESTIONS[2]])
    [other_question] = get_questions(db, other_game)

    with pytest.raises(ValueError, match="not part of"):
        save_answer(db, session_id, other_question.id, "went", 1000)


def test_save_answer_rejects_unknown_session(
    db: Session, played: tuple[int, list[int]]
) -> None:
    _, question_ids = played

    with pytest.raises(NotFoundError, match="session"):
        save_answer(db, 999, question_ids[0], "12", 1000)


def test_save_answer_rejects_unknown_question(
    db: Session, played: tuple[int, list[int]]
) -> None:
    session_id, _ = played

    with pytest.raises(NotFoundError, match="question"):
        save_answer(db, session_id, 999, "12", 1000)


def test_save_answer_rejects_negative_time(
    db: Session, played: tuple[int, list[int]]
) -> None:
    session_id, question_ids = played

    with pytest.raises(ValueError, match="time_ms"):
        save_answer(db, session_id, question_ids[0], "12", -1)


# --- answering a question twice ---


def test_save_answer_rejects_second_answer_to_same_question(
    db: Session, played: tuple[int, list[int]]
) -> None:
    session_id, question_ids = played
    save_answer(db, session_id, question_ids[0], "12", 1000)

    with pytest.raises(DuplicateAnswerError, match="already answered"):
        save_answer(db, session_id, question_ids[0], "11", 300)

    [answer] = saved_answers(db)
    assert answer.chosen_text == "12"


def test_same_question_can_be_answered_in_two_sessions(
    db: Session, played: tuple[int, list[int]]
) -> None:
    first_session, question_ids = played
    game_id = db.get(PlaySession, first_session).game_id
    second_session = start_session(db, game_id, "Ari", "test")

    save_answer(db, first_session, question_ids[0], "12", 1000)
    save_answer(db, second_session, question_ids[0], "11", 1000)

    assert len(saved_answers(db)) == 2


def test_unique_constraint_blocks_duplicate_answer_rows(
    db: Session, played: tuple[int, list[int]]
) -> None:
    """The database itself refuses a second row, even without save_answer."""
    session_id, question_ids = played

    def row() -> Answer:
        return Answer(
            session_id=session_id,
            question_id=question_ids[0],
            chosen_text="12",
            is_correct=True,
            time_ms=1000,
        )

    db.add(row())
    db.commit()
    db.add(row())
    with pytest.raises(IntegrityError):
        db.commit()


def test_save_answer_turns_constraint_error_into_duplicate_error(
    db: Session, played: tuple[int, list[int]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two requests at the same moment both pass the read check; the constraint wins."""
    session_id, question_ids = played
    save_answer(db, session_id, question_ids[0], "12", 1000)
    monkeypatch.setattr(storage, "has_answer", lambda *args: False)

    with pytest.raises(DuplicateAnswerError, match="already answered"):
        save_answer(db, session_id, question_ids[0], "11", 300)

    assert len(saved_answers(db)) == 1
