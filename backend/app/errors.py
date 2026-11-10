"""Errors shared by the generation steps.

GenerationError lives in its own module so that other modules can use it.
"""


class GenerationError(Exception):
    """The model's reply could not be turned into a valid result."""
