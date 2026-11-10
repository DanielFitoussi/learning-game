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
        """The instructions of the first call (the generation call)."""
        return self.calls[0][0]

    @property
    def material(self) -> str:
        """The material of the first call (the generation call)."""
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
        "code_checked": True,
        "exercise": {"a": 7, "op": "+", "b": 5},
    }


def name_of(prompt: str) -> str:
    """The name that question_dict put at the start of the prompt."""
    return prompt.split(NAME_SEPARATOR)[0]


def names(result: Any) -> list[str]:
    return [name_of(question.prompt) for question in result.questions]


def unchecked(question: dict[str, Any]) -> dict[str, Any]:
    """The same question without a math check, so only other rules apply."""
    return question | {"code_checked": False, "exercise": None}


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


def review_reply(*oks: bool) -> str:
    """A review reply with one verdict per reviewed question, in order."""
    reviews = [
        {"index": i, "ok": ok, "problem": None if ok else "Not clear."}
        for i, ok in enumerate(oks)
    ]
    return json.dumps({"reviews": reviews})


def generate(reply: str, count: int = 2, material: str = MATERIAL) -> Any:
    model = FakeTextModel(reply)
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
    model = FakeTextModel(reply_with([question_dict()]))
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
        "code_checked": False,
        "exercise": None,
    }
    model = FakeTextModel(reply_with([question]), review_reply(True))
    result = generate_questions(model, "english", "animals", MATERIAL, 1)
    assert [option.text for option in result.questions[0].options] == [
        "cat",
        "dog",
        "hat",
    ]


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
            # Unchecked, so only the map rejects it (not check_math).
            unchecked(question_with_tags("bad", "concat", "forgot_to_carry")),
        ]
    )
    model = FakeTextModel(reply)
    result = generate_questions(model, subject, chapter, MATERIAL, 2)
    assert names(result) == ["good"]
    assert result.rejected == 1


def test_any_tag_is_allowed_when_no_map() -> None:
    question = unchecked(question_with_tags("free", "forgot_to_carry", "misread"))
    model = FakeTextModel(reply_with([question]), review_reply(True))
    result = generate_questions(model, "math", "addition", MATERIAL, 1)
    assert len(result.questions) == 1
    assert result.rejected == 0


# --- Review of questions without an exercise --------------------------------------------


def test_math_only_questions_are_not_reviewed() -> None:
    model = FakeTextModel(reply_with([question_dict("a"), question_dict("b")]))
    result = generate_questions(model, "math", "addition", MATERIAL, 2)
    assert len(model.calls) == 1
    assert result.review_rejected == 0


def test_question_rejected_by_review_is_rejected_and_counted() -> None:
    reply = reply_with(
        [unchecked(question_dict("good")), unchecked(question_dict("bad"))]
    )
    model = FakeTextModel(reply, review_reply(True, False))
    result = generate_questions(model, "math", "addition", MATERIAL, 2)
    assert names(result) == ["good"]
    assert result.review_rejected == 1
    assert result.rejected == 1


def test_only_questions_without_exercise_are_reviewed() -> None:
    reply = reply_with(
        [
            question_dict("math"),
            unchecked(question_dict("words")),
            question_dict("more"),
        ]
    )
    model = FakeTextModel(reply, review_reply(True))
    result = generate_questions(model, "math", "addition", MATERIAL, 3)

    assert len(model.calls) == 2
    reviewed = json.loads(model.calls[1][1])["questions"]
    assert [name_of(item["prompt"]) for item in reviewed] == ["words"]
    # Order of the questions is kept.
    assert names(result) == ["math", "words", "more"]


def test_review_happens_before_cutting_to_count() -> None:
    # The first question fails the review, so the extra one fills its place.
    reply = reply_with([unchecked(question_dict("bad")), question_dict("extra")])
    model = FakeTextModel(reply, review_reply(False))
    result = generate_questions(model, "math", "addition", MATERIAL, 1)
    assert names(result) == ["extra"]


def test_all_rejected_by_review_raises() -> None:
    reply = reply_with([unchecked(question_dict("bad"))])
    model = FakeTextModel(reply, review_reply(False))
    with pytest.raises(GenerationError):
        generate_questions(model, "math", "addition", MATERIAL, 1)


# --- Math check --------------------------------------------------------------------------


def test_instructions_ask_for_exercise() -> None:
    assert '"exercise"' in build_instructions("math", MAPPED_CHAPTER, 3)


def test_math_question_that_fails_check_is_rejected() -> None:
    wrong_answer = question_dict("wrong answer")
    wrong_answer["options"][0]["text"] = "13"  # 7 + 5 is not 13
    reply = reply_with([question_dict("good"), wrong_answer])
    result = generate(reply)
    assert names(result) == ["good"]
    assert result.rejected == 1


def test_math_question_with_wrong_tag_is_rejected() -> None:
    # 75 is a concat mistake, and 11 is a count mistake: swapping tags fails.
    reply = reply_with(
        [question_dict("good"), question_with_tags("swapped", "count", "concat")]
    )
    result = generate(reply)
    assert names(result) == ["good"]
    assert result.rejected == 1


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
