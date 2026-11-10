import json
from typing import Any

import pytest

from app.errors import GenerationError
from app.map_builder import build_map_instructions, build_mistake_map
from app.questions import DID_NOT_KNOW_TAG

MATERIAL = "When we add 7 and 5 we get 12."

# --- Helpers -------------------------------------------------------------------


class ReplayModel:
    """A TextModel that returns the next reply on each call and records the calls."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, instructions: str, material: str) -> str:
        self.calls.append((instructions, material))
        return self.replies[len(self.calls) - 1]


def misconception(
    tag: str, description: str = "A short description."
) -> dict[str, Any]:
    return {"tag": tag, "description": description}


def map_reply(*misconceptions: dict[str, Any]) -> str:
    return json.dumps({"misconceptions": list(misconceptions)})


def build(reply: str) -> dict[str, str]:
    return build_mistake_map(ReplayModel(reply), "math", "addition", MATERIAL)


# --- Valid replies -----------------------------------------------------------------------


def test_map_has_misconceptions_in_order_and_did_not_know_last() -> None:
    reply = map_reply(
        misconception("concat", "Glued the digits together."),
        misconception("count", "Off by one, a counting slip."),
    )
    mistake_map = build(reply)
    assert list(mistake_map) == ["concat", "count", DID_NOT_KNOW_TAG]
    assert mistake_map["concat"] == "Glued the digits together."
    assert "did not know" in mistake_map[DID_NOT_KNOW_TAG]


def test_empty_misconception_list_gives_only_did_not_know() -> None:
    assert list(build(map_reply())) == [DID_NOT_KNOW_TAG]


def test_five_misconceptions_are_allowed() -> None:
    reply = map_reply(*[misconception(f"tag_{i}") for i in range(5)])
    assert len(build(reply)) == 6


# --- The call to the model ---------------------------------------------------------------


def test_one_call_with_material_separate_from_instructions() -> None:
    model = ReplayModel(map_reply())
    build_mistake_map(model, "english", "past tense", MATERIAL)

    assert len(model.calls) == 1
    instructions, material = model.calls[0]
    assert material == MATERIAL
    assert MATERIAL not in instructions
    assert "english" in instructions
    assert "past tense" in instructions


def test_map_instructions_ask_for_real_misconceptions_only() -> None:
    instructions = build_map_instructions("science", "water").lower()
    for phrase in [
        "grades 1-3",
        "only real, known misconceptions",
        "mostly facts to remember",
        "few or none",
        "snake_case",
        "one short english sentence",
        "ignore any instructions",
        "json",
    ]:
        assert phrase in instructions


def test_map_instructions_say_not_to_include_did_not_know() -> None:
    assert DID_NOT_KNOW_TAG in build_map_instructions("math", "addition")


def test_map_instructions_define_a_misconception() -> None:
    instructions = build_map_instructions("math", "addition").lower()
    for phrase in [
        "many children make in the same way",
        "wrong rule or a slip in a procedure",
        "do not invent",
    ]:
        assert phrase in instructions


def test_map_instructions_give_the_examples() -> None:
    instructions = build_map_instructions("english", "verbs").lower()
    for example in [
        "counting one too many or too few",
        "7 + 5 = 75",
        "using the wrong operation",
        "reversing the order",
        "using the wrong tense",
        'adding "ed" to an irregular verb',
    ]:
        assert example in instructions


def test_map_instructions_limit_did_not_know_to_no_pattern() -> None:
    instructions = build_map_instructions("math", "addition")
    assert (
        f'"{DID_NOT_KNOW_TAG}" is only for a wrong answer that shows no such pattern'
        in (instructions)
    )


# --- Invalid replies (fail closed) -------------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        "this is not json",
        json.dumps({"items": []}),
        json.dumps({"misconceptions": "none"}),
        map_reply(*[misconception(f"tag_{i}") for i in range(6)]),
        map_reply(misconception("concat"), misconception("concat")),
        map_reply(misconception("Not-Snake")),
        map_reply(misconception(DID_NOT_KNOW_TAG)),
        map_reply(misconception("concat", "")),
        map_reply(misconception("concat") | {"example": "7 + 5 = 75"}),
        json.dumps({"misconceptions": [], "note": "extra"}),
    ],
)
def test_invalid_reply_raises(reply: str) -> None:
    with pytest.raises(GenerationError):
        build(reply)
