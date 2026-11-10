"""Errors shared by the generation steps.

GenerationError lives in its own module so that generation.py and
map_builder.py can both use it without importing each other.
"""


class GenerationError(Exception):
    """The model's reply could not be turned into a valid result."""
