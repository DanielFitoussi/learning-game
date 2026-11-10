import json
from pathlib import Path
from typing import Any

import pytest

from app.generation import GenerationResult
from app.questions import Question
from app.try_generation import format_result, main

# --- Helpers -------------------------------------------------------------------


class FakeTextModel:
    """A TextModel that always returns the same reply."""

    def __init__(self, reply: str) -> None:
        self.reply = reply

    def complete_json(self, instructions: str, material: str) -> str:
        return self.reply


def question_dict() -> dict[str, Any]:
    return {
        "kind": "choose_one",
        "subject": "math",
        "chapter": "addition",
        "prompt": "7 + 5 = ?",
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
        "exercise": {"a": 7, "op": "+", "b": 5},
    }


def make_result(rejected: int = 0) -> GenerationResult:
    return GenerationResult(
        questions=[Question.model_validate(question_dict())], rejected=rejected
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
    assert "7 + 5 = ?" in text
    assert "✓" in line_containing(text, "12")
    assert "✓" not in line_containing(text, "75")


def test_format_result_shows_tag_and_hint_for_wrong_options() -> None:
    text = format_result(make_result())
    concat_line = line_containing(text, "75")
    assert "concat" in concat_line
    assert "Add the numbers, do not glue them." in concat_line
    count_line = line_containing(text, "11")
    assert "count" in count_line
    assert "Count again carefully." in count_line


def test_format_result_shows_returned_and_rejected_counts() -> None:
    summary = format_result(make_result(rejected=3)).splitlines()[-1]
    assert "1" in summary
    assert "rejected 3" in summary


# --- main -----------------------------------------------------------------------------


def test_main_prints_result_and_writes_out_file(
    material_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_file = tmp_path / "out.txt"
    model = FakeTextModel(json.dumps({"questions": [question_dict()]}))

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
