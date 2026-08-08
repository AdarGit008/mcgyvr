import re

MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def is_leap(year):
    return (year % 4 == 0 and year % 100 != 0) or year % 400 == 0


def day_index(year, month, day):
    prior = year - 1
    total = 365 * prior + prior // 4 - prior // 100 + prior // 400
    for m in range(1, month):
        total += MONTH_DAYS[m - 1] + (1 if m == 2 and is_leap(year) else 0)
    return total + day - 1


def week_opening(index):
    # Index 0 is 0001-01-01, a Monday, so weekday 2 is Wednesday.
    weekday = index % 7
    return index - ((weekday - 2) % 7)


def meridian_week_label(date: str) -> str:
    if not isinstance(date, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) is None:
        raise ValueError("date must be zero-padded YYYY-MM-DD")
    year = int(date[0:4])
    month = int(date[5:7])
    day = int(date[8:10])
    if year < 2 or year > 9999:
        raise ValueError("year must lie in 0002..9999")
    if month < 1 or month > 12:
        raise ValueError("month must lie in 01..12")
    held = MONTH_DAYS[month - 1] + (1 if month == 2 and is_leap(year) else 0)
    if day < 1 or day > held:
        raise ValueError("the month does not hold that day")
    opening = week_opening(day_index(year, month, day))
    label_year = year
    anchor = week_opening(day_index(year, 1, 8))
    if opening < anchor:
        label_year = year - 1
        anchor = week_opening(day_index(label_year, 1, 8))
    week = (opening - anchor) // 7 + 1
    return f"{label_year:04d}-W{week:02d}"
