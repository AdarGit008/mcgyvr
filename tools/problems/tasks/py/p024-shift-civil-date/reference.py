import re

MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _month_length(year: int, month: int) -> int:
    if month == 2 and _is_leap(year):
        return 29
    return MONTH_DAYS[month - 1]


def _to_day_number(y: int, m: int, d: int) -> int:
    yy = y - 1 if m <= 2 else y
    era = yy // 400
    yoe = yy - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _from_day_number(z: int) -> tuple[int, int, int]:
    z += 719468
    era = z // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    return (y + 1 if m <= 2 else y, m, d)


def shift_civil_date(date: str, days: int) -> str:
    if not isinstance(date, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) is None:
        raise ValueError("date must be zero-padded YYYY-MM-DD")
    if not isinstance(days, int) or isinstance(days, bool):
        raise ValueError("days must be an integer")
    year = int(date[0:4])
    month = int(date[5:7])
    day = int(date[8:10])
    if year < 1:
        raise ValueError("year is before 0001")
    if month < 1 or month > 12:
        raise ValueError("month outside 01..12")
    if day < 1 or day > _month_length(year, month):
        raise ValueError("day does not exist in that month")
    y, m, d = _from_day_number(_to_day_number(year, month, day) + days)
    if y < 1 or y > 9999:
        raise ValueError("result leaves years 0001..9999")
    return f"{y:04d}-{m:02d}-{d:02d}"
