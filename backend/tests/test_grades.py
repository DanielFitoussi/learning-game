import pytest

from app.grades import check_grade


@pytest.mark.parametrize("grade", [1, 2, 3])
def test_check_grade_accepts_grades_1_to_3(grade: int) -> None:
    check_grade(grade)


@pytest.mark.parametrize("grade", [0, 4, -1])
def test_check_grade_rejects_other_grades(grade: int) -> None:
    with pytest.raises(ValueError, match="grade"):
        check_grade(grade)
