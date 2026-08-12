def dur_hours(minutes: int) -> int:
    return minutes // 60


def dur_text(minutes: int) -> str:
    hours = dur_hours(minutes)
    rest = minutes - hours * 60
    if hours and rest:
        return str(hours) + "h" + str(rest) + "m"
    if hours:
        return str(hours) + "h"
    return str(rest) + "m"
