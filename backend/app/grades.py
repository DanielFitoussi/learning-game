"""The school grades we make games for.

This is the only place the list is defined. It lives in its own module so that
generation, storage and the API can all use it without importing each other.
"""

GRADES = (1, 2, 3)


def check_grade(grade: int) -> None:
    """Raise ValueError if the grade is not one we make games for."""
    if grade not in GRADES:
        raise ValueError(f"grade must be one of {GRADES}, got {grade}")
