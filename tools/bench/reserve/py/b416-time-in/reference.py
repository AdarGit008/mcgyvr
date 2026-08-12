def time_in(minute: int, opens: int, closes: int) -> bool:
    """Whether a minute of the day falls inside a window."""
    if opens <= closes:
        return opens <= minute < closes
    return minute >= opens or minute < closes
