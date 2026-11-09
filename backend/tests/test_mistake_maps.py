import re

import pytest

from app.diagnosis import MistakeType
from app.mistake_maps import MISTAKE_MAPS, get_mistake_tags
from app.questions import MISTAKE_TAG_PATTERN


def test_found() -> None:
    tags = get_mistake_tags("math", "addition and subtraction")
    assert tags == {
        "count": "off by one, a counting slip (7 + 5 = 11)",
        "op": "used the other operation (9 - 4 = 13)",
        "concat": "glued the digits together (7 + 5 = 75)",
        "reverse": "reversed the digits of the answer (9 + 3 = 21)",
    }


@pytest.mark.parametrize(
    ("subject", "chapter"),
    [("math", "multiplication"), ("english", "addition and subtraction")],
)
def test_not_found(subject: str, chapter: str) -> None:
    assert get_mistake_tags(subject, chapter) is None


def test_case_and_spaces_are_ignored() -> None:
    tags = get_mistake_tags(" Math ", "Addition   and  SUBTRACTION")
    assert tags is not None
    assert set(tags) == {"count", "op", "concat", "reverse"}


def test_returned_map_is_a_copy() -> None:
    tags = get_mistake_tags("math", "addition and subtraction")
    assert tags is not None
    tags["new_tag"] = "changed by a caller"
    assert "new_tag" not in get_mistake_tags("math", "addition and subtraction")


def test_all_tags_are_snake_case() -> None:
    # Otherwise Question would reject every answer that uses the tag.
    for tags in MISTAKE_MAPS.values():
        for tag in tags:
            assert re.fullmatch(MISTAKE_TAG_PATTERN, tag), tag


def test_math_tags_match_diagnosis_mistake_types() -> None:
    # Generated tags and diagnosed mistakes should use the same names.
    tags = get_mistake_tags("math", "addition and subtraction")
    assert tags is not None
    assert set(tags) <= {mistake.value for mistake in MistakeType}
