import re

LENGTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
SHAPE = re.compile(r"\d{4}-\d{2}-\d{2}")
MOVE_CAP = 5000


def _leaps(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _stamp_of(year, month, day):
    shifted = year - 1 if month <= 2 else year
    era = shifted // 400
    year_of_era = shifted - era * 400
    day_of_year = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    day_of_era = year_of_era * 365 + year_of_era // 4 - year_of_era // 100 + day_of_year
    return era * 146097 + day_of_era - 719468


def _spell(stamp):
    shifted = stamp + 719468
    era = shifted // 146097
    day_of_era = shifted - era * 146097
    year_of_era = (
        day_of_era - day_of_era // 1460 + day_of_era // 36524 - day_of_era // 146096
    ) // 365
    year = year_of_era + era * 400
    day_of_year = day_of_era - (365 * year_of_era + year_of_era // 4 - year_of_era // 100)
    marker = (5 * day_of_year + 2) // 153
    day = day_of_year - (153 * marker + 2) // 5 + 1
    month = marker + 3 if marker < 10 else marker - 9
    if month <= 2:
        year += 1
    return "{:04d}-{:02d}-{:02d}".format(year, month, day)


def _read_date(text):
    if not isinstance(text, str) or SHAPE.fullmatch(text) is None:
        raise ValueError("a date must read YYYY-MM-DD")
    year = int(text[0:4])
    month = int(text[5:7])
    day = int(text[8:10])
    if year < 1900 or year > 2999:
        raise ValueError("the year must lie between 1900 and 2999")
    if month < 1 or month > 12:
        raise ValueError("the month must lie between 01 and 12")
    held = 29 if month == 2 and _leaps(year) else LENGTHS[month - 1]
    if day < 1 or day > held:
        raise ValueError("the day does not exist in its month")
    return _stamp_of(year, month, day)


LOW = _stamp_of(1900, 1, 1)
HIGH = _stamp_of(2999, 12, 31)


def _within(stamp):
    if stamp < LOW or stamp > HIGH:
        raise ValueError("the walk leaves the years 1900 through 2999")
    return stamp


def advance_working_days(start: str, count: int, closures: list) -> str:
    stamp = _read_date(start)
    if not isinstance(count, int) or isinstance(count, bool):
        raise ValueError("the move must be a whole number")
    if count < -MOVE_CAP or count > MOVE_CAP:
        raise ValueError("the move may not pass " + str(MOVE_CAP) + " either way")
    if not isinstance(closures, list):
        raise ValueError("the shut days must be a list")
    shut = set()
    for closure in closures:
        marked = _read_date(closure)
        if marked in shut:
            raise ValueError("a shut day is named twice")
        shut.add(marked)

    def works(at):
        return (at + 3) % 7 < 5 and at not in shut

    if count == 0:
        while not works(stamp):
            stamp = _within(stamp + 1)
        return _spell(stamp)
    step = 1 if count > 0 else -1
    left = abs(count)
    while left > 0:
        stamp = _within(stamp + step)
        if works(stamp):
            left -= 1
    return _spell(stamp)
