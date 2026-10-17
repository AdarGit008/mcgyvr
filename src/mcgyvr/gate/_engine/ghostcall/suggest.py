"""Fuzzy-match an unknown attribute against the real attributes of a parent object."""

from difflib import get_close_matches
from typing import Any


def suggest(name: str, parent: Any, n: int = 3, cutoff: float = 0.6) -> list[str]:
    """Return up to `n` real attribute names of `parent` that closely match `name`."""
    try:
        candidates = [a for a in dir(parent) if not a.startswith("_")]
    except Exception:
        return []
    return get_close_matches(name, candidates, n=n, cutoff=cutoff)
