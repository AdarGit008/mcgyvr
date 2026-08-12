def pad_time(hour: int, minute: int) -> str:
    """An hour and a minute written as a clock reading."""
    h = "0" + str(hour) if hour < 10 else str(hour)
    m = "0" + str(minute) if minute < 10 else str(minute)
    return h + ":" + m
