from typing import Any

import pytest
from pydantic import ValidationError

from app.questions import AnswerOption, Exercise, Question

# --- Helpers -------------------------------------------------------------------


def correct_option(text: str = "12") -> dict[str, Any]:
    return {"text": text, "is_correct": True, "mistake_tag": None, "hint": None}


AUTO_HINT = "<auto>"
"""Marker: give the option its own hint, based on its text."""


def wrong_option(
    text: str,
    mistake_tag: str | None = "concat",
    hint: str | None = AUTO_HINT,
) -> dict[str, Any]:
    # Hints must be unique per question, so the default hint uses the text.
    if hint == AUTO_HINT:
        hint = f"A hint about {text}."
    return {
        "text": text,
        "is_correct": False,
        "mistake_tag": mistake_tag,
        "hint": hint,
    }


def math_options() -> list[dict[str, Any]]:
    return [
        correct_option("12"),
        wrong_option("75", "concat", "Add the numbers, do not glue them."),
        wrong_option("11", "count", "Count again carefully."),
        wrong_option("21", "reverse", "Check the order of the digits."),
    ]


def make_math_question(**changes: Any) -> Question:
    """Build a valid math question, with some fields replaced."""
    data: dict[str, Any] = {
        "kind": "choose_one",
        "subject": "math",
        "chapter": "addition and subtraction",
        "prompt": "7 + 5 = ?",
        "options": math_options(),
        "code_checked": True,
        "exercise": {"a": 7, "op": "+", "b": 5},
    }
    data.update(changes)
    return Question.model_validate(data)


def make_english_question(**changes: Any) -> Question:
    """Build a valid English question, with some fields replaced."""
    data: dict[str, Any] = {
        "kind": "choose_one",
        "subject": "english",
        "chapter": "animals",
        "prompt": "Which animal says 'meow'?",
        "options": [
            correct_option("cat"),
            wrong_option("dog", "similar_meaning", "A dog barks. Which animal meows?"),
            wrong_option(
                "hat",
                "similar_sound",
                "'Hat' sounds like 'cat', but it is not an animal.",
            ),
        ],
        "code_checked": False,
    }
    data.update(changes)
    return Question.model_validate(data)


# --- Valid questions ---------------------------------------------------------------


def test_valid_math_question() -> None:
    question = make_math_question()
    assert question.kind == "choose_one"
    assert question.subject == "math"
    assert question.code_checked is True
    assert len(question.options) == 4
    assert question.options[0] == AnswerOption(
        text="12", is_correct=True, mistake_tag=None, hint=None
    )


def test_valid_english_question() -> None:
    question = make_english_question()
    assert question.subject == "english"
    assert question.code_checked is False
    assert question.exercise is None
    assert len(question.options) == 3


# --- Exercise -------------------------------------------------------------------------


@pytest.mark.parametrize("op", ["+", "-"])
def test_valid_exercise(op: str) -> None:
    exercise = Exercise.model_validate({"a": 7, "op": op, "b": 5})
    assert (exercise.a, exercise.op, exercise.b) == (7, op, 5)


@pytest.mark.parametrize(
    "data",
    [
        {"a": -1, "op": "+", "b": 5},
        {"a": 7, "op": "+", "b": -1},
        {"a": 7, "op": "*", "b": 5},
        {"a": 7, "op": "+", "b": 5, "c": 1},
    ],
)
def test_invalid_exercise_is_rejected(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Exercise.model_validate(data)


def test_math_question_has_exercise() -> None:
    assert make_math_question().exercise == Exercise(a=7, op="+", b=5)


def test_code_checked_question_needs_exercise() -> None:
    with pytest.raises(ValidationError, match="exercise"):
        make_math_question(exercise=None)


def test_question_without_code_check_may_skip_exercise() -> None:
    assert make_english_question(exercise=None).exercise is None


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


# --- Rule 1: exactly one correct option ------------------------------------------------


def test_no_correct_option_is_rejected() -> None:
    options = [wrong_option("75"), wrong_option("11"), wrong_option("21")]
    with pytest.raises(ValidationError, match="exactly one"):
        make_math_question(options=options)


def test_two_correct_options_are_rejected() -> None:
    options = [correct_option("12"), correct_option("twelve"), wrong_option("75")]
    with pytest.raises(ValidationError, match="exactly one"):
        make_math_question(options=options)


# --- Rule 2: a wrong option needs a mistake_tag and a hint ---------------------------


@pytest.mark.parametrize("missing", [None, ""])
def test_wrong_option_needs_mistake_tag(missing: str | None) -> None:
    with pytest.raises(ValidationError):
        AnswerOption.model_validate(wrong_option("75", mistake_tag=missing))


@pytest.mark.parametrize("missing", [None, "", "   "])
def test_wrong_option_needs_hint(missing: str | None) -> None:
    with pytest.raises(ValidationError):
        AnswerOption.model_validate(wrong_option("75", hint=missing))


# --- Rule 3: the correct option has no mistake_tag and no hint ------------------------


def test_correct_option_cannot_have_mistake_tag() -> None:
    data = correct_option() | {"mistake_tag": "concat"}
    with pytest.raises(ValidationError, match="correct option"):
        AnswerOption.model_validate(data)


def test_correct_option_cannot_have_hint() -> None:
    data = correct_option() | {"hint": "Well done!"}
    with pytest.raises(ValidationError, match="correct option"):
        AnswerOption.model_validate(data)


# --- Rule 4: 3 to 4 options ---------------------------------------------------------------


@pytest.mark.parametrize("count", [3, 4])
def test_allowed_number_of_options(count: int) -> None:
    question = make_math_question(options=math_options()[:count])
    assert len(question.options) == count


def test_too_few_options_are_rejected() -> None:
    with pytest.raises(ValidationError):
        make_math_question(options=math_options()[:2])


def test_too_many_options_are_rejected() -> None:
    options = [*math_options(), wrong_option("2", "op", "Look at the sign again.")]
    with pytest.raises(ValidationError):
        make_math_question(options=options)


# --- Rule 5: option texts are unique ----------------------------------------------------


def test_duplicate_option_texts_are_rejected() -> None:
    options = [correct_option("12"), wrong_option("75"), wrong_option("75")]
    with pytest.raises(ValidationError, match="unique"):
        make_math_question(options=options)


def test_wrong_options_with_same_mistake_tag_are_rejected() -> None:
    options = [
        correct_option("12"),
        wrong_option("75", "concat"),
        wrong_option("57", "concat"),
    ]
    with pytest.raises(ValidationError, match="mistake_tag"):
        make_math_question(options=options)


@pytest.mark.parametrize(
    ("first_hint", "second_hint"),
    [
        ("Count again.", "Count again."),
        ("Count again.", "  count AGAIN. "),
    ],
)
def test_wrong_options_with_same_hint_are_rejected(
    first_hint: str, second_hint: str
) -> None:
    options = [
        correct_option("12"),
        wrong_option("75", "concat", first_hint),
        wrong_option("11", "count", second_hint),
    ]
    with pytest.raises(ValidationError, match="hints"):
        make_math_question(options=options)


def test_duplicate_check_ignores_case_and_spaces() -> None:
    options = [correct_option("cat"), wrong_option("dog"), wrong_option(" Cat ")]
    with pytest.raises(ValidationError, match="unique"):
        make_math_question(options=options)


# --- Rule 6: mistake_tag is snake_case --------------------------------------------------


@pytest.mark.parametrize("tag", ["concat", "off_by_1", "similar_sound"])
def test_valid_mistake_tags(tag: str) -> None:
    option = AnswerOption.model_validate(wrong_option("75", mistake_tag=tag))
    assert option.mistake_tag == tag


@pytest.mark.parametrize("tag", ["Concat", "1st", "off-by-one", "off by one", "_x", ""])
def test_invalid_mistake_tags_are_rejected(tag: str) -> None:
    with pytest.raises(ValidationError):
        AnswerOption.model_validate(wrong_option("75", mistake_tag=tag))


# --- Other fields --------------------------------------------------------------------------


def test_unknown_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_math_question(kind="ordering")


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_math_question(dificulty="easy")
