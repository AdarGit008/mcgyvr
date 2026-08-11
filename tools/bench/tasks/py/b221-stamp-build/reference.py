"""Rank a firmware release as one sortable stamp."""

FIELD = 1000


def stamp_build(major: int, minor: int, patch: int) -> int:
    for part in (major, minor, patch):
        if isinstance(part, bool) or not isinstance(part, int):
            raise ValueError("each component must be a whole number")
        if part < 0:
            raise ValueError("each component must not be negative")
    if minor >= FIELD or patch >= FIELD:
        raise ValueError("minor and patch each fill three digits only")
    return (major * FIELD + minor) * FIELD + patch
