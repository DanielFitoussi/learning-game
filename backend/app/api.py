"""The web API.

Run inside backend/:
    uv run --env-file .env fastapi dev app/api.py
"""

import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from functools import cache
from typing import Annotated

import openai
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StringConstraints, field_validator
from sqlalchemy import Engine
from sqlmodel import Session

from app.db import create_tables, database_url, make_engine
from app.errors import DuplicateAnswerError, GenerationError, NotFoundError
from app.generation import MAX_MATERIAL_CHARS, MAX_QUESTIONS, generate_questions
from app.grades import check_grade
from app.llm import OpenAITextModel
from app.modes import Mode
from app.questions import NonEmptyStr
from app.storage import (
    count_questions,
    get_game,
    get_questions,
    save_answer,
    save_game,
    start_session,
)
from app.text_model import TextModel

logger = logging.getLogger(__name__)

MAX_PLAYER_NAME_CHARS = 40

DEFAULT_COUNT = 5
GENERATION_FAILED = "Could not create questions from this material. Please try again."


class TextModelNotConfigured(Exception):
    """The text model could not be created, for example OPENAI_MODEL is missing."""


# --- Dependencies ----------------------------------------------------------------


@cache
def get_engine() -> Engine:
    """The database engine, created once on first use from DATABASE_URL."""
    return make_engine(database_url())


def get_db() -> Iterator[Session]:
    """A database session for one request."""
    with Session(get_engine()) as session:
        yield session


def get_text_model() -> TextModel:
    """The real text model. Its settings come from the environment."""
    try:
        return OpenAITextModel()
    except RuntimeError as error:
        raise TextModelNotConfigured(str(error)) from error


DbSession = Annotated[Session, Depends(get_db)]
Model = Annotated[TextModel, Depends(get_text_model)]


# --- App -------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create the database tables when the server starts."""
    create_tables(get_engine())
    yield


app = FastAPI(title="Learning Quest", lifespan=lifespan)


def short_validation_message(error: RequestValidationError) -> str:
    """One short line per problem, like "grade: ...". The input is not echoed back."""
    lines = []
    for item in error.errors():
        field = ".".join(str(part) for part in item["loc"] if part != "body")
        message = item["msg"].removeprefix("Value error, ")
        lines.append(f"{field}: {message}" if field else message)
    return "; ".join(lines)


@app.exception_handler(RequestValidationError)
async def handle_bad_input(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": short_validation_message(error)},
    )


@app.exception_handler(GenerationError)
@app.exception_handler(openai.OpenAIError)
@app.exception_handler(TextModelNotConfigured)
async def handle_generation_failure(request: Request, error: Exception) -> JSONResponse:
    """The model could not give us questions. Log the reason, tell the client little."""
    logger.error("Question generation failed: %r", error, exc_info=error)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": GENERATION_FAILED},
    )


@app.exception_handler(NotFoundError)
async def handle_not_found(request: Request, error: NotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(error)}
    )


@app.exception_handler(DuplicateAnswerError)
async def handle_duplicate_answer(
    request: Request, error: DuplicateAnswerError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={"detail": str(error)}
    )


def bad_input(error: ValueError) -> HTTPException:
    """A 422 with the error's short message."""
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
    )


# --- POST /games -----------------------------------------------------------------


class CreateGameRequest(BaseModel):
    subject: NonEmptyStr
    chapter: NonEmptyStr
    grade: int
    mode: Mode
    material: str = Field(max_length=MAX_MATERIAL_CHARS)
    count: int = Field(default=DEFAULT_COUNT, ge=1, le=MAX_QUESTIONS)

    @field_validator("grade")
    @classmethod
    def grade_is_allowed(cls, grade: int) -> int:
        check_grade(grade)
        return grade

    @field_validator("material")
    @classmethod
    def material_is_not_blank(cls, material: str) -> str:
        if not material.strip():
            raise ValueError("material must not be empty")
        return material


class CreateGameResponse(BaseModel):
    game_id: int
    question_count: int
    rejected: int


@app.post(
    "/games", status_code=status.HTTP_201_CREATED, response_model=CreateGameResponse
)
def create_game(
    body: CreateGameRequest, db: DbSession, model: Model
) -> CreateGameResponse:
    """Generate questions from the material and save them as a new game.

    A plain `def`, so FastAPI runs it in a thread and the slow model call does
    not block other requests.
    """
    try:
        result = generate_questions(
            model,
            body.subject,
            body.chapter,
            body.material,
            body.count,
            grade=body.grade,
        )
    except ValueError as error:
        raise bad_input(error) from error

    game_id = save_game(
        db, body.subject, body.chapter, body.grade, body.mode, result.questions
    )
    return CreateGameResponse(
        game_id=game_id,
        question_count=len(result.questions),
        rejected=result.rejected,
    )


# --- GET /games/{game_id} --------------------------------------------------------


class GameInfo(BaseModel):
    subject: str
    chapter: str
    grade: int
    mode: Mode
    question_count: int


@app.get("/games/{game_id}", response_model=GameInfo)
def read_game(game_id: int, db: DbSession) -> GameInfo:
    """What a game is about and how it is played. No questions or answers."""
    game = get_game(db, game_id)
    return GameInfo(
        subject=game.subject,
        chapter=game.chapter,
        grade=game.grade,
        mode=game.mode,
        question_count=count_questions(db, game_id),
    )


# --- POST /games/{game_id}/sessions ----------------------------------------------

PlayerName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=MAX_PLAYER_NAME_CHARS
    ),
]


class StartSessionRequest(BaseModel):
    """Only the player's name. The mode comes from the game.

    Extra fields are ignored, so an older client that still sends "mode" works,
    but its value is never used.
    """

    player_name: PlayerName


class StartSessionResponse(BaseModel):
    session_id: int


@app.post(
    "/games/{game_id}/sessions",
    status_code=status.HTTP_201_CREATED,
    response_model=StartSessionResponse,
)
def create_session(
    game_id: int, body: StartSessionRequest, db: DbSession
) -> StartSessionResponse:
    """Start a session of one child playing one game."""
    try:
        session_id = start_session(db, game_id, body.player_name)
    except ValueError as error:
        raise bad_input(error) from error
    return StartSessionResponse(session_id=session_id)


# --- GET /games/{game_id}/questions ----------------------------------------------


class PlayQuestion(BaseModel):
    """A question as the child sees it: option texts only, never which is correct."""

    id: int
    prompt: str
    options: list[str]


@app.get("/games/{game_id}/questions", response_model=list[PlayQuestion])
def list_questions(game_id: int, db: DbSession) -> list[PlayQuestion]:
    """The game's questions in order."""
    return [
        PlayQuestion(
            id=question.id,
            prompt=question.prompt,
            options=[option["text"] for option in question.options],
        )
        for question in get_questions(db, game_id)
    ]


# --- POST /sessions/{session_id}/answers -----------------------------------------


class AnswerRequest(BaseModel):
    question_id: int
    chosen_text: str
    time_ms: int = Field(ge=0)


class AnswerResponse(BaseModel):
    """Only whether the answer was right. The correct answer is never sent."""

    is_correct: bool


@app.post(
    "/sessions/{session_id}/answers",
    status_code=status.HTTP_201_CREATED,
    response_model=AnswerResponse,
)
def answer_question(
    session_id: int, body: AnswerRequest, db: DbSession
) -> AnswerResponse:
    """Save a child's answer to one question."""
    try:
        is_correct = save_answer(
            db, session_id, body.question_id, body.chosen_text, body.time_ms
        )
    except ValueError as error:
        raise bad_input(error) from error
    return AnswerResponse(is_correct=is_correct)
