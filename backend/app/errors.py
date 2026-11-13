"""Errors shared by several modules.

They live in their own module so that any module can raise or catch them.
"""


class GenerationError(Exception):
    """The model's reply could not be turned into a valid result."""


class NotFoundError(Exception):
    """A game, session or question that does not exist."""


class DuplicateAnswerError(Exception):
    """The session has already answered this question."""
