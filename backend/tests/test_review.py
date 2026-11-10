import json
from typing import Any

import pytest

from app.questions import Question
from app.review import (
    NO_REASON,
    NO_VALID_REVIEW,
    ReviewVerdict,
    build_review_instructions,
    review_questions,
)

# --- Helpers -------------------------------------------------------------------


class ReplayModel:
    """A TextModel that returns the next reply on each call and records the calls."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, instructions: str, material: str) -> str:
        self.calls.append((instructions, material))
        return self.replies[len(self.calls) - 1]


def english_question(prompt: str) -> Question:
    return Question.model_validate(
        {
            "kind": "choose_one",
            "subject": "english",
            "chapter": "animals",
            "prompt": prompt,
            "options": [
                {"text": "cat", "is_correct": True, "mistake_tag": None, "hint": None},
                {
                    "text": "dog",
                    "is_correct": False,
                    "mistake_tag": "similar_meaning",
                    "hint": "A dog barks.",
                },
                {
                    "text": "hat",
                    "is_correct": False,
                    "mistake_tag": "similar_sound",
                    "hint": "A hat is not an animal.",
                },
            ],
        }
    )


QUESTIONS = [english_question("Which animal says 'meow'?"), english_question("Q2")]


def review(index: int, ok: bool, problem: str | None = None) -> dict[str, Any]:
    return {"index": index, "ok": ok, "problem": problem}


def reviews_reply(*reviews: dict[str, Any]) -> str:
    return json.dumps({"reviews": list(reviews)})


MISTAKE_MAP = {
    "similar_sound": "Mixed up words that sound alike.",
    "did_not_know": "The child did not know this; no specific misconception.",
}


def run_review(
    reply: str, questions: list[Question] = QUESTIONS
) -> list[ReviewVerdict]:
    return review_questions(ReplayModel(reply), questions, MISTAKE_MAP)


def oks(verdicts: list[ReviewVerdict]) -> list[bool]:
    return [verdict.ok for verdict in verdicts]


def problems(verdicts: list[ReviewVerdict]) -> list[str | None]:
    return [verdict.problem for verdict in verdicts]


# --- Verdicts --------------------------------------------------------------------------


def test_all_ok() -> None:
    verdicts = run_review(reviews_reply(review(0, True), review(1, True)))
    assert oks(verdicts) == [True, True]
    assert problems(verdicts) == [None, None]


def test_one_not_ok_keeps_the_problem_text() -> None:
    reply = reviews_reply(review(0, True), review(1, False, "Two options are correct."))
    verdicts = run_review(reply)
    assert oks(verdicts) == [True, False]
    assert problems(verdicts) == [None, "Two options are correct."]


def test_ok_review_has_no_problem_even_if_text_is_given() -> None:
    reply = reviews_reply(review(0, True, "Looks fine."), review(1, True))
    assert problems(run_review(reply)) == [None, None]


def test_not_ok_without_text_gets_a_fixed_reason() -> None:
    reply = reviews_reply(review(0, True), review(1, False, None))
    assert problems(run_review(reply)) == [None, NO_REASON]


def test_reviews_in_any_order() -> None:
    verdicts = run_review(reviews_reply(review(1, False, "Unclear."), review(0, True)))
    assert oks(verdicts) == [True, False]
    assert problems(verdicts) == [None, "Unclear."]


@pytest.mark.parametrize(
    "reply",
    [
        "this is not json",
        json.dumps({"items": []}),
        json.dumps({"reviews": "all good"}),
        json.dumps({"reviews": [review(0, True) | {"score": 5}, review(1, True)]}),
        json.dumps({"reviews": [review(0, True), {"index": 1, "ok": "yes"}]}),
    ],
)
def test_invalid_reply_means_all_not_ok(reply: str) -> None:
    verdicts = run_review(reply)
    assert oks(verdicts) == [False, False]
    assert problems(verdicts) == [NO_VALID_REVIEW, NO_VALID_REVIEW]


def test_missing_index_is_not_ok() -> None:
    verdicts = run_review(reviews_reply(review(0, True)))
    assert oks(verdicts) == [True, False]
    assert problems(verdicts) == [None, NO_VALID_REVIEW]


def test_index_out_of_range_is_ignored() -> None:
    reply = reviews_reply(review(0, True), review(1, True), review(7, False))
    assert oks(run_review(reply)) == [True, True]


def test_conflicting_reviews_keep_the_first_problem() -> None:
    reply = reviews_reply(
        review(0, True),
        review(1, True),
        review(1, False, "First problem."),
        review(1, False, "Second problem."),
    )
    verdicts = run_review(reply)
    assert oks(verdicts) == [True, False]
    assert problems(verdicts) == [None, "First problem."]


# --- The call to the model -------------------------------------------------------------


def test_empty_list_does_not_call_the_model() -> None:
    model = ReplayModel()
    assert review_questions(model, [], MISTAKE_MAP) == []
    assert model.calls == []


def test_questions_and_map_are_sent_in_one_call_as_json() -> None:
    model = ReplayModel(reviews_reply(review(0, True), review(1, True)))
    review_questions(model, QUESTIONS, MISTAKE_MAP)

    assert len(model.calls) == 1
    instructions, material = model.calls[0]
    assert instructions == build_review_instructions()
    sent = json.loads(material)
    assert sent["mistake_map"] == MISTAKE_MAP
    assert [item["index"] for item in sent["questions"]] == [0, 1]
    assert [item["prompt"] for item in sent["questions"]] == [
        "Which animal says 'meow'?",
        "Q2",
    ]


def test_review_instructions_cover_the_checks() -> None:
    instructions = build_review_instructions().lower()
    for phrase in [
        "really correct",
        "no other option is also correct",
        "clear for a child",
        "subject and chapter",
        "hint fits the mistake of its option",
        "does not give away the answer",
        "mistake_tag fits that option",
        "did_not_know",
        "mistake_map",
        "all six checks",
        "json",
    ]:
        assert phrase in instructions
