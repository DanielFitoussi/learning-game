"""Fixed mistake tags per chapter, used to guide question generation."""

MISTAKE_MAPS: dict[tuple[str, str], dict[str, str]] = {
    ("math", "addition and subtraction"): {
        "count": "off by one, a counting slip (7 + 5 = 11)",
        "op": "used the other operation (9 - 4 = 13)",
        "concat": "glued the digits together (7 + 5 = 75)",
        "reverse": "reversed the digits of the answer (9 + 3 = 21)",
    },
}
"""(subject, chapter) -> {mistake_tag: short English description}."""


def _normalize(text: str) -> str:
    """Lowercase, with single spaces and no spaces at the ends."""
    return " ".join(text.split()).casefold()


def get_mistake_tags(subject: str, chapter: str) -> dict[str, str] | None:
    """Return a copy of the chapter's mistake tags, or None if it has no map.

    The lookup ignores case and extra spaces.
    """
    wanted = (_normalize(subject), _normalize(chapter))
    for (map_subject, map_chapter), tags in MISTAKE_MAPS.items():
        if (_normalize(map_subject), _normalize(map_chapter)) == wanted:
            return dict(tags)
    return None
