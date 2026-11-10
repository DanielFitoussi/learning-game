from typing import Any

import pytest

from app.math_check import check_math
from app.questions import Question

# --- Helpers -------------------------------------------------------------------


def option(text: str, tag: str | None = None) -> dict[str, Any]:
    """A correct option when tag is None, otherwise a wrong option with a hint."""
    if tag is None:
        return {"text": text, "is_correct": True, "mistake_tag": None, "hint": None}
    # Each wrong option gets its own hint, because hints must be unique.
    hint = f"A hint about {text}."
    return {"text": text, "is_correct": False, "mistake_tag": tag, "hint": hint}


def make_question(
    options: list[dict[str, Any]], exercise: dict[str, Any] | None
) -> Question:
    return Question.model_validate(
        {
            "kind": "choose_one",
            "subject": "math",
            "chapter": "addition and subtraction",
            "prompt": "Solve the exercise.",
            "options": options,
            "code_checked": exercise is not None,
            "exercise": exercise,
        }
    )


SEVEN_PLUS_FIVE = {"a": 7, "op": "+", "b": 5}


def good_options() -> list[dict[str, Any]]:
    return [
        option("12"),
        option("75", "concat"),
        option("11", "count"),
        option("21", "reverse"),
    ]


# --- Good questions -------------------------------------------------------------------


def test_good_question_has_no_problems() -> None:
    assert check_math(make_question(good_options(), SEVEN_PLUS_FIVE)) == []


def test_good_subtraction_question_has_no_problems() -> None:
    options = [
        option("5"),
        option("13", "op"),
        option("94", "concat"),
        option("6", "count"),
    ]
    question = make_question(options, {"a": 9, "op": "-", "b": 4})
    assert check_math(question) == []


def test_question_without_exercise_is_not_checked() -> None:
    # Not math-checked, so even nonsense answers give no problems here.
    options = [option("cat"), option("dog", "similar_meaning"), option("hat", "rhyme")]
    assert check_math(make_question(options, None)) == []


# --- Problems ----------------------------------------------------------------------------


def test_wrong_correct_answer_is_a_problem() -> None:
    options = good_options()
    options[0] = option("13")
    problems = check_math(make_question(options, SEVEN_PLUS_FIVE))
    assert len(problems) == 1
    assert "13" in problems[0]
    assert "12" in problems[0]


@pytest.mark.parametrize("text", ["twelve", "12.0", "012", "+75", "-0", "١٢"])
def test_option_that_is_not_a_whole_number_is_a_problem(text: str) -> None:
    options = good_options()
    options[1] = option(text, "concat")
    problems = check_math(make_question(options, SEVEN_PLUS_FIVE))
    assert len(problems) == 1
    assert text in problems[0]
    assert "whole number" in problems[0]


def test_correct_option_that_is_not_a_number_is_a_problem() -> None:
    options = good_options()
    options[0] = option("twelve")
    problems = check_math(make_question(options, SEVEN_PLUS_FIVE))
    assert len(problems) == 1
    assert "whole number" in problems[0]


def test_distractor_with_wrong_tag_is_a_problem() -> None:
    # 75 is a concat mistake for 7 + 5, but it is tagged "op".
    options = [option("12"), option("75", "op"), option("11", "count")]
    problems = check_math(make_question(options, SEVEN_PLUS_FIVE))
    assert len(problems) == 1
    assert "75" in problems[0]
    assert '"op"' in problems[0]
    assert '"concat"' in problems[0]


def test_all_problems_are_reported() -> None:
    options = [option("13"), option("75", "op"), option("eleven", "count")]
    assert len(check_math(make_question(options, SEVEN_PLUS_FIVE))) == 3
