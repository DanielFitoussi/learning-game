import json
from typing import Any

import pytest

from app.generation import (
    MAX_MATERIAL_CHARS,
    MAX_QUESTIONS,
    GenerationError,
    build_instructions,
    generate_questions,
)
from app.llm import JSON_REMINDER, OpenAITextModel
from app.map_builder import build_map_instructions
from app.questions import DID_NOT_KNOW_TAG

MATERIAL = "When we add 7 and 5 we get 12. Adding means putting groups together."


# --- Helpers -------------------------------------------------------------------


class FakeTextModel:
    """A TextModel that returns the next reply on each call and records the calls.

    A call with no reply left fails the test, so an unexpected extra call
    (for example an unwanted review) is caught.
    """

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, instructions: str, material: str) -> str:
        self.calls.append((instructions, material))
        assert len(self.calls) <= len(self.replies), "unexpected extra model call"
        return self.replies[len(self.calls) - 1]

    @property
    def instructions(self) -> str:
        """The instructions of the question call (after the map call)."""
        return self.calls[1][0]

    @property
    def material(self) -> str:
        """The material of the question call (after the map call)."""
        return self.calls[1][1]


HEBREW_PROMPT = "כמה זה 7 + 5?"
NAME_SEPARATOR = ": "


def question_dict(name: str = "q") -> dict[str, Any]:
    """A valid math question. The name lets tests tell questions apart."""
    return {
        "kind": "choose_one",
        "subject": "math",
        "chapter": "addition",
        "prompt": f"{name}{NAME_SEPARATOR}{HEBREW_PROMPT}",
        "options": [
            {"text": "12", "is_correct": True, "mistake_tag": None, "hint": None},
            {
                "text": "75",
                "is_correct": False,
                "mistake_tag": "concat",
                "hint": "חברו את המספרים, אל תדביקו אותם.",
            },
            {
                "text": "11",
                "is_correct": False,
                "mistake_tag": "count",
                "hint": "ספרו שוב לאט ובזהירות.",
            },
        ],
    }


def name_of(prompt: str) -> str:
    """The name that question_dict put at the start of the prompt."""
    return prompt.split(NAME_SEPARATOR)[0]


def names(result: Any) -> list[str]:
    return [name_of(question.prompt) for question in result.questions]


def broken_question_dict() -> dict[str, Any]:
    """A question with two correct options."""
    question = question_dict("broken")
    question["options"][1] = {
        "text": "75",
        "is_correct": True,
        "mistake_tag": None,
        "hint": None,
    }
    return question


def reply_with(questions: list[Any]) -> str:
    return json.dumps({"questions": questions})


def map_reply(*misconceptions: dict[str, str]) -> str:
    return json.dumps({"misconceptions": list(misconceptions)})


DEFAULT_MAP_REPLY = map_reply(
    {"tag": "concat", "description": "Glued the digits together."},
    {"tag": "count", "description": "Off by one, a counting slip."},
)
"""A map with the tags that question_dict uses."""


def review_reply(*oks: bool) -> str:
    """A review reply with one verdict per reviewed question, in order."""
    reviews = [
        {"index": i, "ok": ok, "problem": None if ok else "Not clear."}
        for i, ok in enumerate(oks)
    ]
    return json.dumps({"reviews": reviews})


ALL_OK_REVIEW = review_reply(*[True] * 20)
"""More "ok" reviews than any test needs. Extra indexes are ignored by the review."""


def generate(reply: str, count: int = 2, material: str = MATERIAL) -> Any:
    """Generate with the default map, the given reply, and an all-ok review."""
    model = FakeTextModel(DEFAULT_MAP_REPLY, reply, ALL_OK_REVIEW)
    return generate_questions(model, "math", "addition", material, count)


# --- Valid and partly valid replies ----------------------------------------------


def test_valid_reply_returns_all_questions() -> None:
    reply = reply_with([question_dict("a"), question_dict("b")])
    result = generate(reply)
    assert names(result) == ["a", "b"]
    assert result.rejected == 0


def test_broken_question_is_skipped_and_counted() -> None:
    reply = reply_with([question_dict(), broken_question_dict()])
    result = generate(reply)
    assert len(result.questions) == 1
    assert result.rejected == 1


def test_item_that_is_not_an_object_is_rejected() -> None:
    result = generate(reply_with([question_dict(), "hello"]))
    assert len(result.questions) == 1
    assert result.rejected == 1


def test_extra_valid_questions_are_cut_to_count() -> None:
    reply = reply_with([question_dict("a"), question_dict("b"), question_dict("c")])
    result = generate(reply, count=2)
    assert names(result) == ["a", "b"]
    assert result.rejected == 0


# --- Bad replies -------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        "this is not json",
        json.dumps({"items": []}),
        json.dumps({"questions": "not a list"}),
        json.dumps([question_dict()]),
    ],
)
def test_reply_without_questions_list_raises(reply: str) -> None:
    with pytest.raises(GenerationError):
        generate(reply)


@pytest.mark.parametrize(
    "questions",
    [[], [broken_question_dict()], [broken_question_dict(), "hello"]],
)
def test_no_valid_questions_raises(questions: list[Any]) -> None:
    with pytest.raises(GenerationError):
        generate(reply_with(questions))


# --- Material and instructions ---------------------------------------------------


def test_material_reaches_model_unchanged_and_not_in_instructions() -> None:
    model = FakeTextModel(
        DEFAULT_MAP_REPLY, reply_with([question_dict()]), ALL_OK_REVIEW
    )
    generate_questions(model, "math", "addition", MATERIAL, 1)
    assert model.material == MATERIAL
    assert MATERIAL not in model.instructions


def test_instructions_contain_subject_chapter_and_count() -> None:
    instructions = build_instructions("english", "animals", 7)
    assert "english" in instructions
    assert "animals" in instructions
    assert "7" in instructions


def test_instructions_ask_for_json() -> None:
    # OpenAI's JSON mode requires the word "JSON" in the instructions.
    assert "JSON" in build_instructions("math", "addition", 3)


def test_instructions_ask_for_plural_hints() -> None:
    assert "plural" in build_instructions("math", "addition", 3)


# --- Language and hints ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("subject", "chapter"), [("math", "addition"), ("english", "animals")]
)
def test_instructions_ask_for_hebrew_prompt_and_hints(
    subject: str, chapter: str
) -> None:
    instructions = build_instructions(subject, chapter, 3)
    assert "prompt and every hint in Hebrew" in instructions
    assert "grades 1-3 in Israel" in instructions


def test_instructions_keep_options_in_the_taught_language() -> None:
    instructions = build_instructions("english", "animals", 3)
    assert "options in the language being taught" in instructions
    assert "English words or sentences" in instructions
    assert "in the language of the material" not in instructions


def test_instructions_set_hint_rules() -> None:
    instructions = build_instructions("english", "animals", 3)
    for phrase in [
        "speaks about the mistake of its own option",
        "never have the same hint",
        "never gives away the correct answer",
    ]:
        assert phrase in instructions


def with_prompt(question: dict[str, Any], prompt: str) -> dict[str, Any]:
    return question | {"prompt": prompt}


def with_hint(question: dict[str, Any], option: int, hint: str) -> dict[str, Any]:
    question["options"][option]["hint"] = hint
    return question


@pytest.mark.parametrize(
    "not_hebrew",
    [
        with_prompt(question_dict("x"), "What is 7 + 5?"),
        with_prompt(question_dict("x"), "7 + 5 = ?"),
        with_hint(question_dict("x"), 2, "Count again carefully."),
    ],
)
def test_question_without_hebrew_prompt_or_hint_is_rejected(
    not_hebrew: dict[str, Any],
) -> None:
    result = generate(reply_with([question_dict("good"), not_hebrew]))
    assert names(result) == ["good"]
    assert result.rejected == 1


def test_english_options_with_hebrew_prompt_and_hints_are_kept() -> None:
    question = {
        "kind": "choose_one",
        "subject": "english",
        "chapter": "animals",
        "prompt": "איזו חיה אומרת 'מיאו'?",
        "options": [
            {"text": "cat", "is_correct": True, "mistake_tag": None, "hint": None},
            {
                "text": "dog",
                "is_correct": False,
                "mistake_tag": "similar_meaning",
                "hint": "כלב נובח. איזו חיה מייללת?",
            },
            {
                "text": "hat",
                "is_correct": False,
                "mistake_tag": "similar_sound",
                "hint": "המילה נשמעת דומה, אבל היא לא חיה.",
            },
        ],
    }
    english_map = map_reply(
        {
            "tag": "similar_meaning",
            "description": "Mixed up words with a related meaning.",
        },
        {"tag": "similar_sound", "description": "Mixed up words that sound alike."},
    )
    model = FakeTextModel(english_map, reply_with([question]), review_reply(True))
    result = generate_questions(model, "english", "animals", MATERIAL, 1)
    assert [option.text for option in result.questions[0].options] == [
        "cat",
        "dog",
        "hat",
    ]


# --- Mistake map -------------------------------------------------------------------------

ONLY_THESE_TAGS = "Use only these mistake tags"
DIFFERENT_MISTAKES = "each wrong option must reveal a different mistake"
SAMPLE_MAP = {
    "concat": "glued the digits together",
    "count": "off by one, a counting slip",
    DID_NOT_KNOW_TAG: "did not know",
}


def test_instructions_list_allowed_tags_when_map_is_given() -> None:
    instructions = build_instructions("math", "addition", 3, SAMPLE_MAP)
    assert ONLY_THESE_TAGS in instructions
    assert "- concat: glued the digits together" in instructions
    assert "- count: off by one, a counting slip" in instructions
    assert f"- {DID_NOT_KNOW_TAG}: did not know" in instructions


def test_instructions_have_open_tags_when_no_map() -> None:
    instructions = build_instructions("math", "addition", 3)
    assert ONLY_THESE_TAGS not in instructions
    assert "snake_case" in instructions


@pytest.mark.parametrize("mistake_tags", [SAMPLE_MAP, None])
def test_instructions_ask_for_different_mistakes(
    mistake_tags: dict[str, str] | None,
) -> None:
    instructions = build_instructions("math", "addition", 3, mistake_tags)
    assert DIFFERENT_MISTAKES in instructions


def test_instructions_use_misconception_tags_only_when_really_shown() -> None:
    instructions = build_instructions("math", "addition", 3, SAMPLE_MAP)
    assert "only when the wrong option really shows that misconception" in instructions
    assert f'Otherwise use "{DID_NOT_KNOW_TAG}"' in instructions
    assert f'"{DID_NOT_KNOW_TAG}" may repeat' in instructions


def question_with_tags(name: str, first_tag: str, second_tag: str) -> dict[str, Any]:
    question = question_dict(name)
    question["options"][1]["mistake_tag"] = first_tag
    question["options"][2]["mistake_tag"] = second_tag
    return question


def test_map_is_built_once_first_and_returned() -> None:
    model = FakeTextModel(
        DEFAULT_MAP_REPLY, reply_with([question_dict()]), ALL_OK_REVIEW
    )
    result = generate_questions(model, "math", "addition", MATERIAL, 1)

    assert len(model.calls) == 3
    map_instructions, map_material = model.calls[0]
    assert map_instructions == build_map_instructions("math", "addition")
    assert map_material == MATERIAL
    assert list(result.mistake_map) == ["concat", "count", DID_NOT_KNOW_TAG]


def test_map_tags_appear_in_question_instructions() -> None:
    model = FakeTextModel(
        DEFAULT_MAP_REPLY, reply_with([question_dict()]), ALL_OK_REVIEW
    )
    generate_questions(model, "math", "addition", MATERIAL, 1)
    assert ONLY_THESE_TAGS in model.instructions
    assert "- concat: Glued the digits together." in model.instructions
    assert f"- {DID_NOT_KNOW_TAG}: " in model.instructions


def test_empty_map_still_generates_did_not_know_questions() -> None:
    question = question_with_tags("facts", DID_NOT_KNOW_TAG, DID_NOT_KNOW_TAG)
    model = FakeTextModel(map_reply(), reply_with([question]), ALL_OK_REVIEW)
    result = generate_questions(model, "science", "water", MATERIAL, 1)
    assert names(result) == ["facts"]
    assert list(result.mistake_map) == [DID_NOT_KNOW_TAG]


def test_question_with_tag_outside_map_is_rejected() -> None:
    reply = reply_with(
        [
            question_with_tags("good", "concat", "count"),
            question_with_tags("bad", "concat", "forgot_to_carry"),
        ]
    )
    result = generate(reply)
    assert names(result) == ["good"]
    assert result.rejected == 1


def test_did_not_know_may_repeat_but_other_tags_may_not() -> None:
    reply = reply_with(
        [
            question_with_tags("repeat_ok", DID_NOT_KNOW_TAG, DID_NOT_KNOW_TAG),
            question_with_tags("repeat_bad", "concat", "concat"),
        ]
    )
    result = generate(reply)
    assert names(result) == ["repeat_ok"]
    assert result.rejected == 1


@pytest.mark.parametrize(
    "bad_map",
    ["this is not json", map_reply({"tag": DID_NOT_KNOW_TAG, "description": "x"})],
)
def test_invalid_map_reply_raises_before_question_call(bad_map: str) -> None:
    model = FakeTextModel(bad_map)
    with pytest.raises(GenerationError):
        generate_questions(model, "math", "addition", MATERIAL, 1)
    assert len(model.calls) == 1


# --- Review --------------------------------------------------------------------------


def test_every_valid_question_is_reviewed_in_one_call() -> None:
    reply = reply_with([question_dict("a"), broken_question_dict(), question_dict("b")])
    model = FakeTextModel(DEFAULT_MAP_REPLY, reply, ALL_OK_REVIEW)
    result = generate_questions(model, "math", "addition", MATERIAL, 3)

    assert len(model.calls) == 3
    reviewed = json.loads(model.calls[2][1])["questions"]
    # Only valid questions are reviewed, in their original order.
    assert [name_of(item["prompt"]) for item in reviewed] == ["a", "b"]
    assert names(result) == ["a", "b"]


def test_question_rejected_by_review_is_rejected_and_counted() -> None:
    reply = reply_with([question_dict("good"), question_dict("bad")])
    model = FakeTextModel(DEFAULT_MAP_REPLY, reply, review_reply(True, False))
    result = generate_questions(model, "math", "addition", MATERIAL, 2)
    assert names(result) == ["good"]
    assert result.review_rejected == 1
    assert result.rejected == 1


def test_review_happens_before_cutting_to_count() -> None:
    # The first question fails the review, so the extra one fills its place.
    reply = reply_with([question_dict("bad"), question_dict("extra")])
    model = FakeTextModel(DEFAULT_MAP_REPLY, reply, review_reply(False, True))
    result = generate_questions(model, "math", "addition", MATERIAL, 1)
    assert names(result) == ["extra"]


def test_all_rejected_by_review_raises() -> None:
    reply = reply_with([question_dict("bad")])
    model = FakeTextModel(DEFAULT_MAP_REPLY, reply, review_reply(False))
    with pytest.raises(GenerationError):
        generate_questions(model, "math", "addition", MATERIAL, 1)


def test_instructions_do_not_ask_for_code_check_fields() -> None:
    instructions = build_instructions("math", "addition", 3)
    assert "exercise" not in instructions
    assert "code_checked" not in instructions


# --- Input limits ---------------------------------------------------------------------


@pytest.mark.parametrize("material", ["", "   \n  ", "x" * (MAX_MATERIAL_CHARS + 1)])
def test_invalid_material_raises(material: str) -> None:
    with pytest.raises(ValueError, match="material"):
        generate(reply_with([question_dict()]), material=material)


def test_material_at_max_length_is_allowed() -> None:
    result = generate(reply_with([question_dict()]), material="x" * MAX_MATERIAL_CHARS)
    assert len(result.questions) == 1


@pytest.mark.parametrize("count", [0, -1, MAX_QUESTIONS + 1])
def test_invalid_count_raises(count: int) -> None:
    with pytest.raises(ValueError, match="count"):
        generate(reply_with([question_dict()]), count=count)


@pytest.mark.parametrize(("material", "count"), [("", 1), (MATERIAL, 0)])
def test_invalid_input_makes_no_model_call(material: str, count: int) -> None:
    model = FakeTextModel()
    with pytest.raises(ValueError):
        generate_questions(model, "math", "addition", material, count)
    assert model.calls == []


@pytest.mark.parametrize("count", [1, MAX_QUESTIONS])
def test_count_at_limits_is_allowed(count: int) -> None:
    result = generate(reply_with([question_dict()]), count=count)
    assert len(result.questions) == 1


# --- OpenAITextModel (no network) ------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "   "])
def test_openai_model_needs_model_name(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
    else:
        monkeypatch.setenv("OPENAI_MODEL", value)
    with pytest.raises(RuntimeError, match="OPENAI_MODEL"):
        OpenAITextModel()


class FakeResponses:
    """Stands in for client.responses and records the create() call."""

    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs

        class Response:
            output_text = '{"questions": []}'

        return Response()


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


def test_openai_model_sends_json_mode_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    client = FakeClient()
    model = OpenAITextModel(client=client)  # type: ignore[arg-type]

    reply = model.complete_json("Answer in JSON.", MATERIAL)

    assert reply == '{"questions": []}'
    assert client.responses.kwargs == {
        "model": "test-model",
        "instructions": "Answer in JSON.",
        "input": [
            {"role": "user", "content": MATERIAL},
            {"role": "user", "content": JSON_REMINDER},
        ],
        "text": {"format": {"type": "json_object"}},
    }
