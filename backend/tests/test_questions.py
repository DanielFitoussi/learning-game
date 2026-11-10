from typing import Any

import pytest
from pydantic import ValidationError

from app.questions import AnswerOption, Question

# --- Helpers -------------------------------------------------------------------


def correct_option(text: str = "12") -> dict[str, Any]:
    return {"text": text, "is_correct": True}


def wrong_option(text: str) -> dict[str, Any]:
    return {"text": text, "is_correct": False}


def math_options() -> list[dict[str, Any]]:
    return [
        correct_option("12"),
        wrong_option("75"),
        wrong_option("11"),
        wrong_option("21"),
    ]


def make_math_question(**changes: Any) -> Question:
    """Build a valid math question, with some fields replaced."""
    data: dict[str, Any] = {
        "kind": "choose_one",
        "subject": "math",
        "chapter": "addition and subtraction",
        "prompt": "7 + 5 = ?",
        "options": math_options(),
    }
    data.update(changes)
    return Question.model_validate(data)


def make_english_question(**changes: Any) -> Question:
    """Build a valid English question, with some fields replaced."""
    data: dict[str, Any] = {
        "kind": "choose_one",
        "subject": "english",
        "chapter": "verbs",
        "prompt": "What is the past of 'go'?",
        "options": [correct_option("went"), wrong_option("goed"), wrong_option("go")],
    }
    data.update(changes)
    return Question.model_validate(data)


# --- Valid questions ---------------------------------------------------------------


def test_valid_math_question() -> None:
    question = make_math_question()
    assert question.kind == "choose_one"
    assert question.subject == "math"
    assert len(question.options) == 4
    assert question.options[0] == AnswerOption(text="12", is_correct=True)


def test_valid_english_question() -> None:
    question = make_english_question()
    assert question.subject == "english"
    assert [option.text for option in question.options] == ["went", "goed", "go"]


# --- Removed fields ------------------------------------------------------------------


@pytest.mark.parametrize(
    "removed_field",
    [{"code_checked": True}, {"exercise": {"a": 7, "op": "+", "b": 5}}],
)
def test_removed_code_check_fields_are_rejected(removed_field: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        make_math_question(**removed_field)


@pytest.mark.parametrize(
    "removed_field", [{"mistake_tag": "concat"}, {"hint": "Count again."}]
)
def test_removed_tag_and_hint_fields_are_rejected(
    removed_field: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        AnswerOption.model_validate(wrong_option("75") | removed_field)


# --- Not-empty text fields -----------------------------------------------------------


@pytest.mark.parametrize("field", ["subject", "chapter", "prompt"])
@pytest.mark.parametrize("value", ["", "   "])
def test_question_text_fields_cannot_be_empty(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        make_math_question(**{field: value})


@pytest.mark.parametrize("value", ["", "   "])
def test_option_text_cannot_be_empty(value: str) -> None:
    with pytest.raises(ValidationError):
        AnswerOption.model_validate(correct_option(value))


def test_text_is_stripped() -> None:
    option = AnswerOption.model_validate(correct_option("  12 "))
    assert option.text == "12"


# --- Exactly one correct option --------------------------------------------------------


def test_no_correct_option_is_rejected() -> None:
    options = [wrong_option("75"), wrong_option("11"), wrong_option("21")]
    with pytest.raises(ValidationError, match="exactly one"):
        make_math_question(options=options)


def test_two_correct_options_are_rejected() -> None:
    options = [correct_option("12"), correct_option("twelve"), wrong_option("75")]
    with pytest.raises(ValidationError, match="exactly one"):
        make_math_question(options=options)


# --- 3 to 4 options -----------------------------------------------------------------------


@pytest.mark.parametrize("count", [3, 4])
def test_allowed_number_of_options(count: int) -> None:
    question = make_math_question(options=math_options()[:count])
    assert len(question.options) == count


def test_too_few_options_are_rejected() -> None:
    with pytest.raises(ValidationError):
        make_math_question(options=math_options()[:2])


def test_too_many_options_are_rejected() -> None:
    options = [*math_options(), wrong_option("2")]
    with pytest.raises(ValidationError):
        make_math_question(options=options)


# --- Option texts are unique ------------------------------------------------------------


def test_duplicate_option_texts_are_rejected() -> None:
    options = [correct_option("12"), wrong_option("75"), wrong_option("75")]
    with pytest.raises(ValidationError, match="unique"):
        make_math_question(options=options)


def test_duplicate_check_ignores_case_and_spaces() -> None:
    options = [correct_option("cat"), wrong_option("dog"), wrong_option(" Cat ")]
    with pytest.raises(ValidationError, match="unique"):
        make_math_question(options=options)


# --- Other fields --------------------------------------------------------------------------


def test_unknown_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_math_question(kind="ordering")


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_math_question(dificulty="easy")
