import sys


def test_python_version_is_3_12() -> None:
    """The project runs on Python 3.12."""
    assert sys.version_info[:2] >= (3, 12)
