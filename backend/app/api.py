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
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Engine
from sqlmodel import Session

from app.db import create_tables, database_url, make_engine
from app.errors import GenerationError
from app.generation import MAX_MATERIAL_CHARS, MAX_QUESTIONS, generate_questions
from app.grades import check_grade
from app.llm import OpenAITextModel
from app.questions import NonEmptyStr
from app.storage import save_game
from app.text_model import TextModel

logger = logging.getLogger(__name__)

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


# --- POST /games -----------------------------------------------------------------


class CreateGameRequest(BaseModel):
    subject: NonEmptyStr
    chapter: NonEmptyStr
    grade: int
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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error

    game_id = save_game(db, body.subject, body.chapter, body.grade, result.questions)
    return CreateGameResponse(
        game_id=game_id,
        question_count=len(result.questions),
        rejected=result.rejected,
    )
