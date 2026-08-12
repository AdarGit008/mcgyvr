"""How many days lie between two proleptic Gregorian calendar dates."""

MONTH_LENGTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def _is_leap(year):
    """Divisible by 4, except centuries, which need divisibility by 400."""
    if year % 400 == 0:
        return True
    if year % 100 == 0:
        return False
    return year % 4 == 0


def _month_length(year, month):
    if month == 2 and _is_leap(year):
        return 29
    return MONTH_LENGTHS[month - 1]


def _to_ordinal(date):
    """Days from the calendar epoch up to and including the given date."""
    year, month, day = date
    for part in date:
        if isinstance(part, bool) or not isinstance(part, int):
            raise ValueError("date components must be integers")
    if month < 1 or month > 12:
        raise ValueError("month outside 1 to 12")
    if day < 1 or day > _month_length(year, month):
        raise ValueError("day outside its month")
    prior = year - 1
    days = prior * 365
    days += prior // 4
    days -= prior // 100
    days += prior // 400
    for earlier in range(1, month):
        days += _month_length(year, earlier)
    return days + day


def span_days(start: list, end: list) -> int:
    origin = _to_ordinal(start)
    target = _to_ordinal(end)
    if origin > target:
        raise ValueError("start date after end date")
    return target - origin
