import json
from pathlib import Path
from typing import Any

import pytest

from app.generation import GenerationResult, ReviewRejection
from app.questions import Question
from app.try_generation import format_result, main

# --- Helpers -------------------------------------------------------------------


class FakeTextModel:
    """A TextModel that returns the next reply on each call (generate, then review)."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)

    def complete_json(self, instructions: str, material: str) -> str:
        return self.replies.pop(0)


ALL_OK_REVIEW = json.dumps({"reviews": [{"index": 0, "ok": True, "problem": None}]})
MAP_REPLY = json.dumps(
    {
        "misconceptions": [
            {"tag": "concat", "description": "Glued the digits together."},
            {"tag": "count", "description": "Off by one, a counting slip."},
        ]
    }
)
MISTAKE_MAP = {
    "concat": "Glued the digits together.",
    "count": "Off by one, a counting slip.",
    "did_not_know": "The child did not know this; no specific misconception.",
}


def question_dict(prompt: str = "כמה זה 7 + 5?") -> dict[str, Any]:
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


def rejection(prompt: str, problem: str) -> ReviewRejection:
    question = Question.model_validate(question_dict(prompt))
    return ReviewRejection(question=question, problem=problem)


def make_result(
    rejected: int = 0, review_rejections: list[ReviewRejection] | None = None
) -> GenerationResult:
    return GenerationResult(
        questions=[Question.model_validate(question_dict())],
        rejected=rejected,
        review_rejections=review_rejections or [],
        mistake_map=MISTAKE_MAP,
    )


def line_containing(text: str, needle: str) -> str:
    return next(line for line in text.splitlines() if needle in line)


@pytest.fixture
def material_file(tmp_path: Path) -> Path:
    path = tmp_path / "material.txt"
    path.write_text("שבע ועוד חמש זה שתים עשרה. 7 + 5 = 12", encoding="utf-8")
    return path


# --- format_result ------------------------------------------------------------------


def test_format_result_shows_prompt_and_marks_correct_option() -> None:
    text = format_result(make_result())
    assert "כמה זה 7 + 5?" in text
    assert "✓" in line_containing(text, "12")
    assert "✓" not in line_containing(text, "75")


def test_format_result_shows_tag_and_hint_for_wrong_options() -> None:
    text = format_result(make_result())
    concat_line = line_containing(text, "75")
    assert "concat" in concat_line
    assert "חברו את המספרים, אל תדביקו אותם." in concat_line
    count_line = line_containing(text, "11")
    assert "count" in count_line
    assert "ספרו שוב לאט ובזהירות." in count_line


def test_format_result_shows_returned_and_rejected_counts() -> None:
    summary = format_result(make_result(rejected=3)).splitlines()[-1]
    assert "1" in summary
    assert "rejected 3" in summary


def test_format_result_shows_the_mistake_map() -> None:
    text = format_result(make_result())
    assert "Mistake map:" in text
    for tag, description in MISTAKE_MAP.items():
        assert f"- {tag}: {description}" in text


TWO_REJECTIONS = [
    rejection("כמה זה 8 + 4?", "Two options are correct."),
    rejection("כמה זה 9 + 3?", "The hint gives away the answer."),
]


def test_format_result_shows_review_rejected_count() -> None:
    result = make_result(rejected=3, review_rejections=TWO_REJECTIONS)
    summary = format_result(result).splitlines()[-1]
    assert "2 by the review" in summary


def test_format_result_shows_questions_rejected_by_the_review() -> None:
    text = format_result(make_result(rejected=2, review_rejections=TWO_REJECTIONS))
    lines = text.splitlines()
    header = lines.index("Rejected by the review:")
    assert lines[header + 1 : header + 3] == [
        "  - כמה זה 8 + 4?: Two options are correct.",
        "  - כמה זה 9 + 3?: The hint gives away the answer.",
    ]
    # The section comes after the questions and before the summary.
    assert header > lines.index("1. כמה זה 7 + 5?")
    assert lines[-1].startswith("Returned")


def test_format_result_leaves_out_review_section_when_nothing_was_rejected() -> None:
    assert "Rejected by the review:" not in format_result(make_result())


# --- main -----------------------------------------------------------------------------


def test_main_prints_result_and_writes_out_file(
    material_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_file = tmp_path / "out.txt"
    model = FakeTextModel(
        MAP_REPLY, json.dumps({"questions": [question_dict()]}), ALL_OK_REVIEW
    )

    code = main(
        [str(material_file), "math", "addition", "1", "--out", str(out_file)],
        model=model,
    )

    expected = format_result(make_result())
    assert code == 0
    assert capsys.readouterr().out.strip() == expected.strip()
    assert out_file.read_text(encoding="utf-8") == expected


def test_main_returns_1_when_reply_is_not_valid(
    material_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_file = tmp_path / "out.txt"
    model = FakeTextModel("this is not json")

    code = main(
        [str(material_file), "math", "addition", "1", "--out", str(out_file)],
        model=model,
    )

    assert code == 1
    assert "JSON" in capsys.readouterr().err
    assert not out_file.exists()


def test_main_returns_1_for_invalid_count(material_file: Path) -> None:
    model = FakeTextModel(json.dumps({"questions": [question_dict()]}))
    assert main([str(material_file), "math", "addition", "0"], model=model) == 1


def test_main_returns_1_when_material_file_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    model = FakeTextModel(json.dumps({"questions": [question_dict()]}))
    missing = tmp_path / "missing.txt"
    assert main([str(missing), "math", "addition", "1"], model=model) == 1
    assert "missing.txt" in capsys.readouterr().err


def test_main_returns_1_when_openai_model_is_not_set(
    material_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # No model is passed, so main creates OpenAITextModel, which fails
    # before any network call because OPENAI_MODEL is missing.
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    assert main([str(material_file), "math", "addition", "1"]) == 1
    assert "OPENAI_MODEL" in capsys.readouterr().err
