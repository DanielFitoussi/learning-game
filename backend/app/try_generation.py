"""Try question generation with the real model from the command line.

Run inside backend/:
    uv run --env-file .env python -m app.try_generation \
        <material_file> <subject> <chapter> <count> [--out <file>]
"""

import argparse
import io
import sys
from pathlib import Path

from app.generation import (
    GenerationError,
    GenerationResult,
    TextModel,
    generate_questions,
)
from app.llm import OpenAITextModel
from app.questions import AnswerOption, Question

CORRECT_MARK = "✓"
WRONG_MARK = "✗"


def _format_option(option: AnswerOption) -> str:
    """One option line: a check mark for the correct one, tag and hint for wrong ones."""
    if option.is_correct:
        return f"   {CORRECT_MARK} {option.text}"
    return f"   {WRONG_MARK} {option.text}  [{option.mistake_tag}] {option.hint}"


def _format_question(number: int, question: Question) -> str:
    """The question prompt followed by its options, one per line."""
    lines = [f"{number}. {question.prompt}"]
    lines += [_format_option(option) for option in question.options]
    return "\n".join(lines)


def _format_mistake_map(mistake_map: dict[str, str]) -> str:
    """The mistake map, one tag and its description per line."""
    lines = ["Mistake map:"]
    lines += [f"  - {tag}: {description}" for tag, description in mistake_map.items()]
    return "\n".join(lines)


def format_result(result: GenerationResult) -> str:
    """The mistake map, then all questions, with a summary line at the end."""
    blocks = [_format_mistake_map(result.mistake_map)]
    blocks += [
        _format_question(number, question)
        for number, question in enumerate(result.questions, start=1)
    ]
    summary = (
        f"Returned {len(result.questions)} questions, rejected {result.rejected}"
        f" ({result.review_rejected} by the review)."
    )
    return "\n\n".join([*blocks, summary]) + "\n"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.try_generation",
        description="Generate questions from a material file with the real model.",
    )
    parser.add_argument("material_file", type=Path, help="UTF-8 text file")
    parser.add_argument("subject", help='for example "math" or "english"')
    parser.add_argument("chapter", help='for example "addition and subtraction"')
    parser.add_argument("count", type=int, help="number of questions to ask for")
    parser.add_argument("--out", type=Path, help="also write the result to this file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, model: TextModel | None = None) -> int:
    """Run the command. Return 0 on success and 1 on a known error."""
    args = _parse_args(argv)
    try:
        # utf-8-sig also accepts files that start with a BOM (Windows Notepad).
        material = args.material_file.read_text(encoding="utf-8-sig")
        text_model = model if model is not None else OpenAITextModel()
        result = generate_questions(
            text_model, args.subject, args.chapter, material, args.count
        )
    except (GenerationError, ValueError, OSError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    text = format_result(result)
    print(text, end="")
    if args.out is not None:
        args.out.write_text(text, encoding="utf-8")
    return 0


def _use_utf8_output() -> None:
    """Print Hebrew and symbols such as ✓ on Windows without UnicodeEncodeError."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    _use_utf8_output()
    sys.exit(main())
