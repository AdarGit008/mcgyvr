import re

LENGTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
SHAPE = re.compile(r"\d{4}-\d{2}-\d{2}")
SPAN_CAP = 40000


def _leaps(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _stamp_of(year, month, day):
    shifted = year - 1 if month <= 2 else year
    era = shifted // 400
    year_of_era = shifted - era * 400
    day_of_year = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    day_of_era = year_of_era * 365 + year_of_era // 4 - year_of_era // 100 + day_of_year
    return era * 146097 + day_of_era - 719468


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


def count_working_days(opening: str, closing: str, weekend: list, holidays: list) -> int:
    first = _read_date(opening)
    last = _read_date(closing)
    if last < first:
        raise ValueError("the closing date falls before the opening one")
    if last - first + 1 > SPAN_CAP:
        raise ValueError("the span runs longer than " + str(SPAN_CAP) + " days")
    if not isinstance(weekend, list):
        raise ValueError("the weekend must be a list")
    closed = set()
    for day in weekend:
        if not isinstance(day, int) or isinstance(day, bool) or day < 0 or day > 6:
            raise ValueError("a weekend day must be a whole number from 0 through 6")
        if day in closed:
            raise ValueError("the weekend names a day twice")
        closed.add(day)
    if len(closed) == 7:
        raise ValueError("the weekend may not name all seven days")
    if not isinstance(holidays, list):
        raise ValueError("the shut dates must be a list")
    shut = set()
    for holiday in holidays:
        stamp = _read_date(holiday)
        if stamp in shut:
            raise ValueError("a shut date is named twice")
        shut.add(stamp)
    worked = 0
    for stamp in range(first, last + 1):
        weekday = (stamp + 3) % 7
        if weekday in closed or stamp in shut:
            continue
        worked += 1
    return worked
