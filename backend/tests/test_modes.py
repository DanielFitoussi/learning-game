import pytest

from app.modes import check_mode


@pytest.mark.parametrize("mode", ["learning", "test"])
def test_check_mode_accepts_learning_and_test(mode: str) -> None:
    check_mode(mode)


@pytest.mark.parametrize("mode", ["practice", "", "Test"])
def test_check_mode_rejects_other_modes(mode: str) -> None:
    with pytest.raises(ValueError, match="mode"):
        check_mode(mode)
