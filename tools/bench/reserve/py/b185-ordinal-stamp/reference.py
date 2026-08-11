WEEKDAYS = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def ordinal_stamp(year, day):
    """Expand a year and a day count into a dated, named log stamp."""
    if not isinstance(year, int) or year < 2000 or year > 2999:
        raise ValueError("year %r is outside 2000 through 2999" % (year,))
    long = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    lengths = [31, 29 if long else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if not isinstance(day, int) or day < 1 or day > (366 if long else 365):
        raise ValueError("day %r is outside year %d" % (day, year))
    month = 0
    left = day
    while left > lengths[month]:
        left -= lengths[month]
        month += 1
    since = day - 1
    for past in range(2000, year):
        since += 366 if past % 4 == 0 and (past % 100 != 0 or past % 400 == 0) else 365
    return "%04d-%02d-%02d %s" % (year, month + 1, left, WEEKDAYS[since % 7])
