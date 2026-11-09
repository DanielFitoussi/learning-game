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

MATERIAL = "When we add 7 and 5 we get 12. Adding means putting groups together."


# --- Helpers -------------------------------------------------------------------


class FakeTextModel:
    """A TextModel that returns a fixed reply and records what it received."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.instructions: str | None = None
        self.material: str | None = None

    def complete_json(self, instructions: str, material: str) -> str:
        self.instructions = instructions
        self.material = material
        return self.reply


def question_dict(prompt: str = "7 + 5 = ?") -> dict[str, Any]:
    return {
        "kind": "choose_one",
        "subject": "math",
        "chapter": "addition",
        "prompt": prompt,
        "options": [
            {"text": "12", "is_correct": True, "mistake_tag": None, "hint": None},
            {
                "text": "75",
                "is_correct": False,
                "mistake_tag": "concat",
                "hint": "Add the numbers, do not glue them.",
            },
            {
                "text": "11",
                "is_correct": False,
                "mistake_tag": "count",
                "hint": "Count again carefully.",
            },
        ],
        "code_checked": True,
    }


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


def generate(reply: str, count: int = 2, material: str = MATERIAL) -> Any:
    model = FakeTextModel(reply)
    return generate_questions(model, "math", "addition", material, count)


# --- Valid and partly valid replies ----------------------------------------------


def test_valid_reply_returns_all_questions() -> None:
    reply = reply_with([question_dict("7 + 5 = ?"), question_dict("6 + 6 = ?")])
    result = generate(reply)
    assert [q.prompt for q in result.questions] == ["7 + 5 = ?", "6 + 6 = ?"]
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
    assert [q.prompt for q in result.questions] == ["a", "b"]
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
    model = FakeTextModel(reply_with([question_dict()]))
    generate_questions(model, "math", "addition", MATERIAL, 1)
    assert model.material == MATERIAL
    assert model.instructions is not None
    assert MATERIAL not in model.instructions


def test_instructions_contain_subject_chapter_and_count() -> None:
    instructions = build_instructions("english", "animals", 7)
    assert "english" in instructions
    assert "animals" in instructions
    assert "7" in instructions


def test_instructions_ask_for_json() -> None:
    # OpenAI's JSON mode requires the word "JSON" in the instructions.
    assert "JSON" in build_instructions("math", "addition", 3)


# --- Mistake maps -----------------------------------------------------------------------

MAPPED_CHAPTER = "addition and subtraction"
ONLY_THESE_TAGS = "Use only these mistake tags"
DIFFERENT_MISTAKES = "each wrong option must reveal a different mistake"


def test_instructions_list_allowed_tags_when_map_exists() -> None:
    instructions = build_instructions("math", MAPPED_CHAPTER, 3)
    assert ONLY_THESE_TAGS in instructions
    for line in [
        "- count: off by one, a counting slip (7 + 5 = 11)",
        "- op: used the other operation (9 - 4 = 13)",
        "- concat: glued the digits together (7 + 5 = 75)",
        "- reverse: reversed the digits of the answer (9 + 3 = 21)",
    ]:
        assert line in instructions


def test_instructions_have_open_tags_when_no_map() -> None:
    instructions = build_instructions("english", "animals", 3)
    assert ONLY_THESE_TAGS not in instructions
    assert "glued the digits together" not in instructions
    assert "snake_case" in instructions


@pytest.mark.parametrize(
    ("subject", "chapter"), [("math", MAPPED_CHAPTER), ("english", "animals")]
)
def test_instructions_ask_for_different_mistakes(subject: str, chapter: str) -> None:
    assert DIFFERENT_MISTAKES in build_instructions(subject, chapter, 3)


def question_with_tags(prompt: str, first_tag: str, second_tag: str) -> dict[str, Any]:
    question = question_dict(prompt)
    question["options"][1]["mistake_tag"] = first_tag
    question["options"][2]["mistake_tag"] = second_tag
    return question


@pytest.mark.parametrize(
    ("subject", "chapter"),
    [("math", MAPPED_CHAPTER), ("Math", " Addition and  Subtraction ")],
)
def test_question_with_tag_outside_map_is_rejected(subject: str, chapter: str) -> None:
    reply = reply_with(
        [
            question_with_tags("good", "concat", "count"),
            question_with_tags("bad", "concat", "forgot_to_carry"),
        ]
    )
    model = FakeTextModel(reply)
    result = generate_questions(model, subject, chapter, MATERIAL, 2)
    assert [q.prompt for q in result.questions] == ["good"]
    assert result.rejected == 1


def test_any_tag_is_allowed_when_no_map() -> None:
    reply = reply_with([question_with_tags("free", "forgot_to_carry", "misread")])
    result = generate(reply, count=1)
    assert len(result.questions) == 1
    assert result.rejected == 0


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
