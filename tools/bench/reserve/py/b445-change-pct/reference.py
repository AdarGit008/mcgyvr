def change_pct(old: int, fresh: int) -> int:
    """The change from an old value to a new one, as a percentage of the old."""
    if old == 0:
        return 0
    return (fresh - old) * 100 // old
