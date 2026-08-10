from solution import shift_months

assert shift_months(2024, 3, 15, 2) == [2024, 5, 15], "shift within the year"
assert shift_months(2024, 11, 30, 3) == [2025, 2, 28], "shift crosses into a short month"
assert shift_months(2024, 1, 31, 1) == [2024, 2, 29], "leap February keeps day 29"
assert shift_months(2023, 1, 31, 1) == [2023, 2, 28], "plain February clamps to 28"
assert shift_months(2024, 5, 20, -6) == [2023, 11, 20], "negative shift crosses the year"
assert shift_months(2024, 2, 29, 12) == [2025, 2, 28], "leap day clamps a year later"
assert shift_months(1999, 7, 4, 0) == [1999, 7, 4], "zero shift returns the date"
assert shift_months(2100, 1, 31, 1) == [2100, 2, 28], "a century year is not a leap year"


def rejects(*args):
    try:
        shift_months(*args)
    except ValueError:
        return True
    return False


assert rejects(2024, 0, 10, 1), "month zero is rejected"
assert rejects(2023, 2, 29, 1), "a day missing from the start month is rejected"
assert rejects(2024, 4, 31, 1), "April has no day 31"
assert rejects(2024, 1, 15, 0.5), "fractional shift is rejected"
print("ok")
