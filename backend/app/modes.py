"""The ways a game can be played. The teacher picks one when creating the game.

This is the only place the list is defined. It lives in its own module so that
models, storage and the API can all use it without importing each other.
"""

from typing import Literal, get_args

Mode = Literal["learning", "test"]

MODES: tuple[str, ...] = get_args(Mode)


def check_mode(mode: str) -> None:
    """Raise ValueError if the mode is not one a game can have."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
