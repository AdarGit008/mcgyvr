"""Calendar-date month arithmetic with day clamping."""


def shift_months(year: int, month: int, day: int, shift: int) -> list:
    month_days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    def month_length(y, m):
        leap = y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)
        if m == 2 and leap:
            return 29
        return month_days[m - 1]

    for value in (year, month, day, shift):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("year, month, day and shift must be integers")
    if month < 1 or month > 12:
        raise ValueError("month must be within 1..12")
    if day < 1 or day > month_length(year, month):
        raise ValueError("day does not exist in the starting month")
    index = year * 12 + (month - 1) + shift
    out_year, rem = divmod(index, 12)
    out_month = rem + 1
    return [out_year, out_month, min(day, month_length(out_year, out_month))]
