"""Classify a child's answers to + and - exercises and find repeated mistakes."""

from collections import Counter
from enum import StrEnum

GUESS_LIMIT_MS = 1500
"""A wrong answer given faster than this is treated as a guess."""

OPERATIONS = ("+", "-")

MIN_PATTERN_COUNT = 2
"""A mistake type must appear at least this many times to be a pattern."""


class MistakeType(StrEnum):
    CORRECT = "correct"
    GUESS = "guess"
    CONCAT = "concat"
    OP = "op"
    COUNT = "count"
    REVERSE = "reverse"
    OTHER = "other"


NEVER_PATTERNS = frozenset({MistakeType.CORRECT, MistakeType.OTHER})
"""Result types that are never reported as patterns."""


def _calculate(a: int, b: int, op: str) -> int:
    """Return the result of `a op b`."""
    return a + b if op == "+" else a - b


def _other_op(op: str) -> str:
    """Return the opposite operation: '+' for '-' and '-' for '+'."""
    return "-" if op == "+" else "+"


def _is_concat(a: int, b: int, answer: int) -> bool:
    """True if the answer is the digits of a and b glued together (7, 5 -> 75)."""
    return str(answer) == f"{a}{b}"


def _reverse_digits(number: int) -> str:
    """Reverse the digits of a number and keep its sign (12 -> '21', -12 -> '-21')."""
    sign = "-" if number < 0 else ""
    return sign + str(abs(number))[::-1]


def _is_reversed(correct: int, answer: int) -> bool:
    """True if the correct answer has 2+ digits and the answer is its digits reversed."""
    has_two_digits = abs(correct) >= 10
    return has_two_digits and str(answer) == _reverse_digits(correct)


def _validate(a: int, b: int, op: str, time_ms: int) -> None:
    """Raise ValueError if the input is not a valid exercise."""
    if op not in OPERATIONS:
        raise ValueError(f"op must be '+' or '-', got {op!r}")
    if a < 0 or b < 0:
        raise ValueError(f"a and b must be non-negative, got a={a}, b={b}")
    if time_ms < 0:
        raise ValueError(f"time_ms must be non-negative, got {time_ms}")


def classify_answer(a: int, b: int, op: str, answer: int, time_ms: int) -> MistakeType:
    """Classify the child's answer to `a op b`.

    The rules are checked in order and the first match wins:
    correct, guess, concat, op, count, reverse, other.
    """
    _validate(a, b, op, time_ms)
    correct = _calculate(a, b, op)

    if answer == correct:
        return MistakeType.CORRECT
    if time_ms < GUESS_LIMIT_MS:
        return MistakeType.GUESS
    if _is_concat(a, b, answer):
        return MistakeType.CONCAT
    if answer == _calculate(a, b, _other_op(op)):
        return MistakeType.OP
    if abs(answer - correct) == 1:
        return MistakeType.COUNT
    if _is_reversed(correct, answer):
        return MistakeType.REVERSE
    return MistakeType.OTHER


def detect_patterns(results: list[MistakeType]) -> dict[MistakeType, int]:
    """Return the mistake types that repeat, with how often each appeared.

    Only types that appear at least MIN_PATTERN_COUNT times are included,
    and correct/other are always skipped. The result is sorted from most
    common to least common; ties keep the order of first appearance.
    """
    counts = Counter(result for result in results if result not in NEVER_PATTERNS)
    return {
        mistake: count
        for mistake, count in counts.most_common()
        if count >= MIN_PATTERN_COUNT
    }
