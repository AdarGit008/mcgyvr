def audit_artist_gaps(playlist: list, spacing: int) -> list:
    """Where a play order crowds one artist too closely."""
    if not isinstance(playlist, list) or not playlist:
        raise ValueError("the playlist must be a list with at least one track")
    if isinstance(spacing, bool) or not isinstance(spacing, int) or spacing < 0:
        raise ValueError("the spacing must be a whole number of zero or more")

    report = []
    last_seen = {}
    for at, artist in enumerate(playlist):
        if not isinstance(artist, str) or artist == "":
            raise ValueError(f"the entry at {at} is not an artist name")
        before = last_seen.get(artist)
        if before is not None:
            between = at - before - 1
            if between < spacing:
                report.append({"artist": artist, "at": at, "between": between})
        last_seen[artist] = at
    return report
