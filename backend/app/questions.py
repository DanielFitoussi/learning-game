"""Data models for a generated question and its answer options."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MIN_OPTIONS = 3
MAX_OPTIONS = 4

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
"""Text with leading/trailing spaces removed, that is not empty afterwards."""


class AnswerOption(BaseModel):
    """One answer a child can pick."""

    model_config = ConfigDict(extra="forbid")

    text: NonEmptyStr
    is_correct: bool


class Question(BaseModel):
    """A generated question with its answer options."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["choose_one"]
    subject: NonEmptyStr
    chapter: NonEmptyStr
    prompt: NonEmptyStr
    options: list[AnswerOption] = Field(min_length=MIN_OPTIONS, max_length=MAX_OPTIONS)

    @model_validator(mode="after")
    def check_options(self) -> Self:
        """Exactly one option is correct, and option texts are unique."""
        correct_count = sum(option.is_correct for option in self.options)
        if correct_count != 1:
            raise ValueError(f"exactly one option must be correct, got {correct_count}")

        texts = [option.text.casefold() for option in self.options]
        if len(texts) != len(set(texts)):
            raise ValueError("option texts must be unique (ignoring case)")
        return self
