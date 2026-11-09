"""Data models for a generated question and its answer options."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MIN_OPTIONS = 3
MAX_OPTIONS = 4

MISTAKE_TAG_PATTERN = r"^[a-z][a-z0-9_]*$"
"""snake_case: lowercase letters, digits and underscores, starting with a letter."""

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
"""Text with leading/trailing spaces removed, that is not empty afterwards."""

MistakeTag = Annotated[str, StringConstraints(pattern=MISTAKE_TAG_PATTERN)]


class AnswerOption(BaseModel):
    """One answer a child can pick."""

    model_config = ConfigDict(extra="forbid")

    text: NonEmptyStr
    is_correct: bool
    mistake_tag: MistakeTag | None
    hint: NonEmptyStr | None

    @model_validator(mode="after")
    def check_tag_and_hint(self) -> Self:
        """A wrong option needs a tag and a hint; the correct option has neither."""
        has_tag_or_hint = self.mistake_tag is not None or self.hint is not None
        has_tag_and_hint = self.mistake_tag is not None and self.hint is not None
        if self.is_correct and has_tag_or_hint:
            raise ValueError("the correct option must not have a mistake_tag or a hint")
        if not self.is_correct and not has_tag_and_hint:
            raise ValueError("a wrong option must have a mistake_tag and a hint")
        return self


class Question(BaseModel):
    """A generated question with its answer options."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["choose_one"]
    subject: NonEmptyStr
    chapter: NonEmptyStr
    prompt: NonEmptyStr
    options: list[AnswerOption] = Field(min_length=MIN_OPTIONS, max_length=MAX_OPTIONS)
    code_checked: bool

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
