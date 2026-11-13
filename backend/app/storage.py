"""Save and load games, play sessions and answers."""

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, func, select

from app import questions
from app.errors import DuplicateAnswerError, NotFoundError
from app.grades import check_grade
from app.models import Answer, Game, PlaySession, Question
from app.modes import check_mode


def save_game(
    db: Session,
    subject: str,
    chapter: str,
    grade: int,
    mode: str,
    game_questions: list[questions.Question],
) -> int:
    """Save a game and its questions in the given order. Returns the game id."""
    check_grade(grade)
    check_mode(mode)

    game = Game(subject=subject, chapter=chapter, grade=grade, mode=mode)
    db.add(game)
    db.flush()  # gives the game its id
    assert game.id is not None

    for position, question in enumerate(game_questions):
        db.add(
            Question(
                game_id=game.id,
                position=position,
                prompt=question.prompt,
                options=[option.model_dump() for option in question.options],
            )
        )
    db.commit()
    return game.id


def get_game(db: Session, game_id: int) -> Game:
    """The game with this id. Raises NotFoundError for an unknown game."""
    game = db.get(Game, game_id)
    if game is None:
        raise NotFoundError(f"game {game_id} does not exist")
    return game


def get_questions(db: Session, game_id: int) -> list[Question]:
    """The questions of a game, in order. Raises NotFoundError for an unknown game."""
    get_game(db, game_id)
    statement = (
        select(Question).where(Question.game_id == game_id).order_by(Question.position)
    )
    return list(db.exec(statement))


def count_questions(db: Session, game_id: int) -> int:
    """How many questions a game has. Raises NotFoundError for an unknown game."""
    get_game(db, game_id)
    statement = (
        select(func.count()).select_from(Question).where(Question.game_id == game_id)
    )
    return db.exec(statement).one()


def start_session(db: Session, game_id: int, player_name: str) -> int:
    """Start a session of one child playing one game. Returns the session id.

    The session's mode comes from the game, never from the client.
    """
    game = get_game(db, game_id)
    name = player_name.strip()
    if not name:
        raise ValueError("player_name must not be empty")

    session = PlaySession(game_id=game_id, player_name=name, mode=game.mode)
    db.add(session)
    db.commit()
    assert session.id is not None
    return session.id


def same_text(a: str, b: str) -> bool:
    """True if the texts are equal, ignoring case and surrounding spaces."""
    return a.strip().casefold() == b.strip().casefold()


def find_option(options: list[dict], chosen_text: str) -> dict | None:
    """The option whose text matches chosen_text, or None."""
    return next(
        (option for option in options if same_text(option["text"], chosen_text)), None
    )


def has_answer(db: Session, session_id: int, question_id: int) -> bool:
    """True if the session has already answered the question."""
    statement = select(Answer.id).where(
        Answer.session_id == session_id, Answer.question_id == question_id
    )
    return db.exec(statement).first() is not None


def save_answer(
    db: Session, session_id: int, question_id: int, chosen_text: str, time_ms: int
) -> bool:
    """Save a child's answer. is_correct is worked out here, never taken from the client.

    Returns whether the answer was correct. Raises NotFoundError for an unknown
    session or question, DuplicateAnswerError if the question was already
    answered in this session, and ValueError for other bad input.
    """
    session = db.get(PlaySession, session_id)
    if session is None:
        raise NotFoundError(f"session {session_id} does not exist")
    question = db.get(Question, question_id)
    if question is None:
        raise NotFoundError(f"question {question_id} does not exist")
    if question.game_id != session.game_id:
        raise ValueError(f"question {question_id} is not part of this session's game")
    if time_ms < 0:
        raise ValueError(f"time_ms must not be negative, got {time_ms}")

    option = find_option(question.options, chosen_text)
    if option is None:
        raise ValueError(f"{chosen_text!r} is not one of the question's options")

    already_answered = f"question {question_id} was already answered in this session"
    # Checking first gives a clear error in the usual case, like a double click.
    if has_answer(db, session_id, question_id):
        raise DuplicateAnswerError(already_answered)

    is_correct = bool(option["is_correct"])
    db.add(
        Answer(
            session_id=session_id,
            question_id=question_id,
            chosen_text=option["text"],
            is_correct=is_correct,
            time_ms=time_ms,
        )
    )
    try:
        db.commit()
    except IntegrityError as error:
        # Two requests at the same moment can both pass the check above; the
        # unique constraint stops the second. The session and question were
        # checked above, so this constraint is the only one that can fail here.
        db.rollback()
        raise DuplicateAnswerError(already_answered) from error
    return is_correct
