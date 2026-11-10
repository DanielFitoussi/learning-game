"""Check math questions in code before they reach a child. No AI is used here."""

import re

from app.diagnosis import GUESS_LIMIT_MS, classify_answer
from app.questions import Exercise, Question

CHECK_TIME_MS = GUESS_LIMIT_MS
"""The fastest time that is not a guess, so classify_answer never returns "guess"."""

WHOLE_NUMBER_PATTERN = re.compile(r"-?(0|[1-9][0-9]*)")
"""A plain whole number: optional minus, no leading zeros, ASCII digits only."""


def _parse_whole_number(text: str) -> int | None:
    """Return the number in `text`, or None if it is not a plain whole number."""
    if not WHOLE_NUMBER_PATTERN.fullmatch(text) or text == "-0":
        return None
    return int(text)


def _result(exercise: Exercise) -> int:
    """The right answer to the exercise."""
    if exercise.op == "+":
        return exercise.a + exercise.b
    return exercise.a - exercise.b


def check_math(question: Question) -> list[str]:
    """Return the math problems in the question. An empty list means it is OK.

    Questions without an exercise are not checked and always return [].
    """
    exercise = question.exercise
    if exercise is None:
        return []

    problems: list[str] = []
    for option in question.options:
        answer = _parse_whole_number(option.text)
        if answer is None:
            problems.append(f'option "{option.text}" is not a whole number')
        elif option.is_correct:
            if answer != _result(exercise):
                problems.append(
                    f'correct option "{option.text}" is wrong: '
                    f"{exercise.a} {exercise.op} {exercise.b} = {_result(exercise)}"
                )
        else:
            mistake = classify_answer(
                exercise.a, exercise.b, exercise.op, answer, CHECK_TIME_MS
            )
            if mistake != option.mistake_tag:
                problems.append(
                    f'option "{option.text}" has mistake_tag "{option.mistake_tag}" '
                    f'but the answer is classified as "{mistake}"'
                )
    return problems
