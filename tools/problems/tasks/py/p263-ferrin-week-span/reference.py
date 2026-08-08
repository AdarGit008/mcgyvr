MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def leaps(year):
    return (year % 4 == 0 and year % 100 != 0) or year % 400 == 0


def opening_weekday(year):
    # Weekday of January 1, with 0 standing for Monday; day 0 of the count
    # is 0001-01-01, itself a Monday.
    prior = year - 1
    index = 365 * prior + prior // 4 - prior // 100 + prior // 400
    return index % 7


def stamp(year, ordinal):
    remaining = ordinal
    for month in range(1, 13):
        held = MONTH_DAYS[month - 1] + (1 if month == 2 and leaps(year) else 0)
        if remaining <= held or month == 12:
            return f"{year:04d}-{month:02d}-{remaining:02d}"
        remaining -= held
    raise ValueError("unreachable")


def whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def ferrin_week_span(year: int, week: int) -> list:
    if not whole(year) or year < 1 or year > 9999:
        raise ValueError("year must be a whole number in 1..9999")
    if not whole(week) or week < 0:
        raise ValueError("week must be a whole number of at least zero")
    span = 366 if leaps(year) else 365
    opening = 1 + (5 - opening_weekday(year)) % 7
    if week == 0:
        if opening == 1:
            raise ValueError("the year opens on a Saturday, so it carries no week 0")
        return [stamp(year, 1), stamp(year, opening - 1)]
    first = opening + 7 * (week - 1)
    if first > span:
        raise ValueError("the year does not reach that week")
    last = min(first + 6, span)
    return [stamp(year, first), stamp(year, last)]
