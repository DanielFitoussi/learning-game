import json
from typing import Any

import pytest

from app.questions import Question
from app.review import build_review_instructions, review_questions

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


def run_review(reply: str, questions: list[Question] = QUESTIONS) -> list[bool]:
    return review_questions(ReplayModel(reply), questions)


# --- Verdicts --------------------------------------------------------------------------


def test_all_ok() -> None:
    assert run_review(reviews_reply(review(0, True), review(1, True))) == [True, True]


def test_one_not_ok() -> None:
    reply = reviews_reply(review(0, True), review(1, False, "Two options are correct."))
    assert run_review(reply) == [True, False]


def test_reviews_in_any_order() -> None:
    assert run_review(reviews_reply(review(1, False), review(0, True))) == [True, False]


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
    assert run_review(reply) == [False, False]


def test_missing_index_is_not_ok() -> None:
    assert run_review(reviews_reply(review(0, True))) == [True, False]


def test_index_out_of_range_is_ignored() -> None:
    reply = reviews_reply(review(0, True), review(1, True), review(7, False))
    assert run_review(reply) == [True, True]


def test_conflicting_reviews_for_one_index_are_not_ok() -> None:
    reply = reviews_reply(review(0, True), review(1, True), review(1, False))
    assert run_review(reply) == [True, False]


# --- The call to the model -------------------------------------------------------------


def test_empty_list_does_not_call_the_model() -> None:
    model = ReplayModel()
    assert review_questions(model, []) == []
    assert model.calls == []


def test_all_questions_are_sent_in_one_call_as_json() -> None:
    model = ReplayModel(reviews_reply(review(0, True), review(1, True)))
    review_questions(model, QUESTIONS)

    assert len(model.calls) == 1
    instructions, material = model.calls[0]
    assert instructions == build_review_instructions()
    sent = json.loads(material)["questions"]
    assert [item["index"] for item in sent] == [0, 1]
    assert [item["prompt"] for item in sent] == ["Which animal says 'meow'?", "Q2"]


def test_review_instructions_cover_the_checks() -> None:
    instructions = build_review_instructions().lower()
    for phrase in [
        "really correct",
        "no other option is also correct",
        "clear for a child",
        "subject and chapter",
        "hint fits the mistake of its option",
        "does not give away the answer",
        "all five checks",
        "json",
    ]:
        assert phrase in instructions
