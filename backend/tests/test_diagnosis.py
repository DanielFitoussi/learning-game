import pytest

from app.diagnosis import (
    MistakeType,
    classify_answer,
    detect_patterns,
)

SLOW_MS = 5000  # Well above the guess limit, so "guess" never triggers.
FAST_MS = 800  # Below the guess limit.


# --- One test per mistake type ---------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "op", "answer"),
    [
        (7, 5, "+", 12),
        (9, 4, "-", 5),
        (0, 0, "+", 0),
        (3, 7, "-", -4),
    ],
)
def test_correct(a: int, b: int, op: str, answer: int) -> None:
    assert classify_answer(a, b, op, answer, SLOW_MS) == MistakeType.CORRECT


def test_guess() -> None:
    assert classify_answer(7, 5, "+", 30, FAST_MS) == MistakeType.GUESS


@pytest.mark.parametrize(
    ("a", "b", "op", "answer"),
    [
        (7, 5, "+", 75),
        (9, 4, "-", 94),
        (12, 3, "+", 123),
    ],
)
def test_concat(a: int, b: int, op: str, answer: int) -> None:
    assert classify_answer(a, b, op, answer, SLOW_MS) == MistakeType.CONCAT


@pytest.mark.parametrize(
    ("a", "b", "op", "answer"),
    [
        (9, 4, "-", 13),
        (7, 5, "+", 2),
        (3, 7, "+", -4),
    ],
)
def test_op(a: int, b: int, op: str, answer: int) -> None:
    assert classify_answer(a, b, op, answer, SLOW_MS) == MistakeType.OP


@pytest.mark.parametrize("answer", [11, 13])
def test_count(answer: int) -> None:
    assert classify_answer(7, 5, "+", answer, SLOW_MS) == MistakeType.COUNT


@pytest.mark.parametrize(
    ("a", "b", "op", "answer"),
    [
        (9, 3, "+", 21),
        (50, 3, "+", 35),
        (3, 15, "-", -21),
    ],
)
def test_reverse(a: int, b: int, op: str, answer: int) -> None:
    assert classify_answer(a, b, op, answer, SLOW_MS) == MistakeType.REVERSE


def test_other() -> None:
    assert classify_answer(7, 5, "+", 40, SLOW_MS) == MistakeType.OTHER


# --- Edge cases from the agreed choices --------------------------------------


def test_concat_compares_text_not_numbers() -> None:
    # 0 and 3 glued is "03", which is not the answer "3".
    # 3 is the result of the other operation (0+3), so it is "op".
    assert classify_answer(0, 3, "-", 3, SLOW_MS) == MistakeType.OP


def test_reverse_with_trailing_zero_is_other() -> None:
    # The right answer is 20. Reversed, that is "02", not "2".
    assert classify_answer(10, 10, "+", 2, SLOW_MS) == MistakeType.OTHER


def test_single_digit_answer_is_never_reverse() -> None:
    # 4 has one digit, so reversing it is not a mistake type.
    assert classify_answer(2, 2, "+", 4, SLOW_MS) == MistakeType.CORRECT
    assert classify_answer(2, 2, "+", 8, SLOW_MS) == MistakeType.OTHER


# --- Rule order ---------------------------------------------------------------


def test_correct_beats_guess() -> None:
    # Right answer, very fast: still correct.
    assert classify_answer(7, 5, "+", 12, 300) == MistakeType.CORRECT


def test_guess_beats_concat() -> None:
    # 75 is a concat answer, but it was given too fast.
    assert classify_answer(7, 5, "+", 75, FAST_MS) == MistakeType.GUESS


def test_op_beats_reverse() -> None:
    # 22-9 = 13. The answer 31 is both 22+9 (op) and 13 reversed (reverse).
    assert classify_answer(22, 9, "-", 31, SLOW_MS) == MistakeType.OP


def test_guess_time_boundary() -> None:
    assert classify_answer(7, 5, "+", 40, 1499) == MistakeType.GUESS
    assert classify_answer(7, 5, "+", 40, 1500) == MistakeType.OTHER


# --- Invalid input ------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "op", "time_ms"),
    [
        (7, 5, "*", SLOW_MS),
        (-1, 5, "+", SLOW_MS),
        (7, -1, "+", SLOW_MS),
        (7, 5, "+", -1),
    ],
)
def test_invalid_input_raises(a: int, b: int, op: str, time_ms: int) -> None:
    with pytest.raises(ValueError):
        classify_answer(a, b, op, 0, time_ms)


# --- detect_patterns ------------------------------------------------------------

CORRECT = MistakeType.CORRECT
GUESS = MistakeType.GUESS
CONCAT = MistakeType.CONCAT
OP = MistakeType.OP
COUNT = MistakeType.COUNT
REVERSE = MistakeType.REVERSE
OTHER = MistakeType.OTHER





def test_pattern_needs_at_least_2_answers() -> None:
    # concat appears twice (a pattern), op only once (not a pattern).
    assert detect_patterns([CONCAT, CONCAT, OP]) == {CONCAT: 2}


def test_no_repeats_means_no_patterns() -> None:
    assert detect_patterns([CONCAT, OP, COUNT]) == {}


def test_correct_and_other_are_never_patterns() -> None:
    results = [CORRECT, CORRECT, CORRECT, OTHER, OTHER, OTHER, COUNT, COUNT]
    assert detect_patterns(results) == {COUNT: 2}


def test_guess_can_be_a_pattern() -> None:
    assert detect_patterns([GUESS, GUESS]) == {GUESS: 2}


def test_patterns_are_sorted_most_common_first() -> None:
    results = [OP, CONCAT, CONCAT, CONCAT, OP, REVERSE, REVERSE, REVERSE, REVERSE]
    # A dict compares equal regardless of order, so check the items as a list.
    assert list(detect_patterns(results).items()) == [
        (REVERSE, 4),
        (CONCAT, 3),
        (OP, 2),
    ]


def test_ties_keep_order_of_first_appearance() -> None:
    results = [OP, CONCAT, CONCAT, OP]
    assert list(detect_patterns(results).items()) == [(OP, 2), (CONCAT, 2)]


def test_empty_list_has_no_patterns() -> None:
    assert detect_patterns([]) == {}


def test_only_correct_answers_has_no_patterns() -> None:
    assert detect_patterns([CORRECT] * 5) == {}
