"""The interface every language model must provide.

It lives in its own module so that generation.py and review.py can both use it
without importing each other.
"""

from typing import Protocol


class TextModel(Protocol):
    """A language model that answers with a JSON string."""

    def complete_json(self, instructions: str, material: str) -> str: ...
