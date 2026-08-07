import re

OFFSETS = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4]
LENGTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def _is_leap(year):
    return (year % 4 == 0 and year % 100 != 0) or year % 400 == 0


def _days_in_month(year, month):
    if month == 2 and _is_leap(year):
        return 29
    return LENGTHS[month - 1]


def _monday_index(year, month, day):
    y = year - 1 if month < 3 else year
    sunday0 = (y + y // 4 - y // 100 + y // 400 + OFFSETS[month - 1] + day) % 7
    return (sunday0 + 6) % 7


def expand_nth_weekday(ordinal: int, weekday: int, start: str, months: int) -> list:
    if (
        not isinstance(ordinal, int)
        or isinstance(ordinal, bool)
        or ordinal == 0
        or ordinal < -1
        or ordinal > 5
    ):
        raise ValueError("ordinal must be -1 or 1..5")
    if not isinstance(weekday, int) or isinstance(weekday, bool) or not 0 <= weekday <= 6:
        raise ValueError("weekday must be 0..6")
    if not isinstance(start, str) or re.fullmatch(r"\d{4}-\d{2}", start) is None:
        raise ValueError("start must be zero-padded YYYY-MM")
    year = int(start[:4])
    month = int(start[5:7])
    if year < 1 or not 1 <= month <= 12:
        raise ValueError("start must name a real month in 0001..9999")
    if not isinstance(months, int) or isinstance(months, bool) or not 1 <= months <= 240:
        raise ValueError("months must be a positive integer of at most 240")

    dates = []
    for _ in range(months):
        if year > 9999:
            raise ValueError("span runs past year 9999")
        length = _days_in_month(year, month)
        opening = _monday_index(year, month, 1)
        first = 1 + (weekday - opening) % 7
        if ordinal == -1:
            day = first + 7 * ((length - first) // 7)
        else:
            day = first + 7 * (ordinal - 1)
        if day <= length:
            dates.append(f"{year:04d}-{month:02d}-{day:02d}")
        month += 1
        if month == 13:
            month = 1
            year += 1
    return dates
