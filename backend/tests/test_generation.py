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
    """A TextModel that returns the next reply on each call and records the calls.

    A call with no reply left fails the test, so an unexpected extra call
    is caught.
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
        """The instructions of the first call (the question call)."""
        return self.calls[0][0]

    @property
    def material(self) -> str:
        """The material of the first call (the question call)."""
        return self.calls[0][1]


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
            {"text": "12", "is_correct": True},
            {"text": "75", "is_correct": False},
            {"text": "11", "is_correct": False},
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
    question["options"][1] = {"text": "75", "is_correct": True}
    return question


def reply_with(questions: list[Any]) -> str:
    return json.dumps({"questions": questions})


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
    """Generate with the given reply and an all-ok review."""
    model = FakeTextModel(reply, ALL_OK_REVIEW)
    return generate_questions(model, "math", "addition", material, count, grade=2)


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


def test_question_with_old_tag_and_hint_fields_is_rejected() -> None:
    old_style = question_dict("old")
    old_style["options"][1] |= {"mistake_tag": "concat", "hint": "חברו את המספרים."}
    result = generate(reply_with([question_dict("new"), old_style]))
    assert names(result) == ["new"]
    assert result.rejected == 1


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


# --- Calls, material and instructions ----------------------------------------------


def test_two_calls_questions_then_review() -> None:
    model = FakeTextModel(reply_with([question_dict()]), ALL_OK_REVIEW)
    generate_questions(model, "math", "addition", MATERIAL, 1, grade=2)
    assert len(model.calls) == 2
    assert model.calls[0][0] == build_instructions("math", "addition", 1, grade=2)


def test_material_reaches_model_unchanged_and_not_in_instructions() -> None:
    model = FakeTextModel(reply_with([question_dict()]), ALL_OK_REVIEW)
    generate_questions(model, "math", "addition", MATERIAL, 1, grade=2)
    assert model.material == MATERIAL
    assert MATERIAL not in model.instructions


def test_instructions_contain_subject_chapter_and_count() -> None:
    instructions = build_instructions("english", "animals", 7, grade=2)
    assert "english" in instructions
    assert "animals" in instructions
    assert "7" in instructions


def test_instructions_ask_for_json() -> None:
    # OpenAI's JSON mode requires the word "JSON" in the instructions.
    assert "JSON" in build_instructions("math", "addition", 3, grade=2)


def test_instructions_ask_for_typical_mistakes() -> None:
    instructions = build_instructions("math", "addition", 3, grade=2)
    for phrase in [
        "typical mistake that children really make",
        "75 for 7 + 5",
        '"goed" for the past of "go"',
        "not a random wrong answer",
        "Wrong options in one question should show different mistakes",
    ]:
        assert phrase in instructions


def test_instructions_drop_tags_and_hints() -> None:
    instructions = build_instructions("math", "addition", 3, grade=2)
    for removed in ["mistake_tag", "hint", "did_not_know"]:
        assert removed not in instructions


# --- Language ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("subject", "chapter"), [("math", "addition"), ("english", "animals")]
)
def test_instructions_ask_for_hebrew_prompt_in_plural(
    subject: str, chapter: str
) -> None:
    instructions = build_instructions(subject, chapter, 3, grade=2)
    assert "Write the prompt in Hebrew" in instructions
    assert "plural" in instructions


def test_instructions_keep_options_in_the_taught_language() -> None:
    instructions = build_instructions("english", "animals", 3, grade=2)
    assert "options in the language being taught" in instructions
    assert "English words or sentences" in instructions


# --- Grade -------------------------------------------------------------------------------


@pytest.mark.parametrize("grade", [1, 2, 3])
def test_instructions_say_the_grade(grade: int) -> None:
    instructions = build_instructions("math", "addition", 3, grade=grade)
    assert f"The children are in grade {grade} in Israel" in instructions


def test_grade_1_instructions_ask_for_simple_text_with_niqqud() -> None:
    instructions = build_instructions("math", "addition", 3, grade=1)
    for phrase in [
        "just learning to read",
        "very short sentences",
        "simple, everyday words",
        "full Hebrew vowel marks (niqqud)",
    ]:
        assert phrase in instructions


@pytest.mark.parametrize("grade", [2, 3])
def test_grade_2_and_3_instructions_ask_for_short_text_without_niqqud(
    grade: int,
) -> None:
    instructions = build_instructions("math", "addition", 3, grade=grade)
    assert "short and clear sentences" in instructions
    assert "niqqud) are not needed" in instructions
    assert "just learning to read" not in instructions
    assert "full Hebrew vowel marks" not in instructions


@pytest.mark.parametrize("grade", [0, 4, -1])
def test_build_instructions_rejects_invalid_grade(grade: int) -> None:
    with pytest.raises(ValueError, match="grade"):
        build_instructions("math", "addition", 3, grade=grade)


def test_invalid_grade_makes_no_model_call() -> None:
    model = FakeTextModel()
    with pytest.raises(ValueError, match="grade"):
        generate_questions(model, "math", "addition", MATERIAL, 1, grade=4)
    assert model.calls == []


def test_prompt_with_niqqud_is_kept() -> None:
    # Grade 1 prompts carry vowel marks; they still count as Hebrew.
    with_niqqud = question_dict("n") | {"prompt": "n: כַּמָּה זֶה 7 + 5?"}
    result = generate(reply_with([with_niqqud]))
    assert names(result) == ["n"]
    assert result.rejected == 0


@pytest.mark.parametrize("prompt", ["What is 7 + 5?", "7 + 5 = ?"])
def test_question_without_hebrew_prompt_is_rejected(prompt: str) -> None:
    not_hebrew = question_dict("x") | {"prompt": prompt}
    result = generate(reply_with([question_dict("good"), not_hebrew]))
    assert names(result) == ["good"]
    assert result.rejected == 1


def test_english_options_with_hebrew_prompt_are_kept() -> None:
    question = {
        "kind": "choose_one",
        "subject": "english",
        "chapter": "verbs",
        "prompt": "מה צורת העבר של 'go'?",
        "options": [
            {"text": "went", "is_correct": True},
            {"text": "goed", "is_correct": False},
            {"text": "go", "is_correct": False},
        ],
    }
    model = FakeTextModel(reply_with([question]), review_reply(True))
    result = generate_questions(model, "english", "verbs", MATERIAL, 1, grade=2)
    assert [option.text for option in result.questions[0].options] == [
        "went",
        "goed",
        "go",
    ]


def test_schema_sent_to_the_model_has_no_tags_or_hints() -> None:
    schema_part = build_instructions("math", "addition", 3, grade=2).split(
        "JSON schema:"
    )[1]
    assert '"text"' in schema_part
    assert '"is_correct"' in schema_part
    assert "mistake_tag" not in schema_part
    assert "hint" not in schema_part


# --- Review --------------------------------------------------------------------------


def test_every_valid_question_is_reviewed_in_one_call() -> None:
    reply = reply_with([question_dict("a"), broken_question_dict(), question_dict("b")])
    model = FakeTextModel(reply, ALL_OK_REVIEW)
    result = generate_questions(model, "math", "addition", MATERIAL, 3, grade=2)

    assert len(model.calls) == 2
    sent = json.loads(model.calls[1][1])
    assert list(sent) == ["questions"]
    # Only valid questions are reviewed, in their original order.
    assert [name_of(item["prompt"]) for item in sent["questions"]] == ["a", "b"]
    assert names(result) == ["a", "b"]


def test_question_rejected_by_review_is_rejected_and_counted() -> None:
    reply = reply_with([question_dict("good"), question_dict("bad")])
    model = FakeTextModel(reply, review_reply(True, False))
    result = generate_questions(model, "math", "addition", MATERIAL, 2, grade=2)
    assert names(result) == ["good"]
    assert result.review_rejected == 1
    assert result.rejected == 1


def test_review_rejections_keep_question_and_problem() -> None:
    reply = reply_with([question_dict("good"), question_dict("bad")])
    model = FakeTextModel(reply, review_reply(True, False))
    result = generate_questions(model, "math", "addition", MATERIAL, 2, grade=2)
    assert [
        (name_of(rejection.question.prompt), rejection.problem)
        for rejection in result.review_rejections
    ] == [("bad", "Not clear.")]


def test_review_happens_before_cutting_to_count() -> None:
    # The first question fails the review, so the extra one fills its place.
    reply = reply_with([question_dict("bad"), question_dict("extra")])
    model = FakeTextModel(reply, review_reply(False, True))
    result = generate_questions(model, "math", "addition", MATERIAL, 1, grade=2)
    assert names(result) == ["extra"]


def test_all_rejected_by_review_raises() -> None:
    reply = reply_with([question_dict("bad")])
    model = FakeTextModel(reply, review_reply(False))
    with pytest.raises(GenerationError):
        generate_questions(model, "math", "addition", MATERIAL, 1, grade=2)


def test_instructions_do_not_ask_for_code_check_fields() -> None:
    instructions = build_instructions("math", "addition", 3, grade=2)
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
        generate_questions(model, "math", "addition", material, count, grade=2)
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
