from solution import shift_civil_date

assert shift_civil_date("2024-02-28", 1) == "2024-02-29", "leap year has Feb 29"
assert shift_civil_date("2023-02-28", 1) == "2023-03-01", "common year skips to March"
assert shift_civil_date("1900-02-28", 1) == "1900-03-01", "century year is not leap"
assert shift_civil_date("2000-02-28", 1) == "2000-02-29", "400-year century is leap"
assert shift_civil_date("2024-01-01", -1) == "2023-12-31", "backward across a year"
assert shift_civil_date("2024-12-31", 1) == "2025-01-01", "forward across a year"
assert shift_civil_date("2024-03-10", 365) == "2025-03-10", "a common-year span"
assert shift_civil_date("2021-06-15", -500) == "2020-02-01", "long negative shift"
assert shift_civil_date("0999-12-31", 1) == "1000-01-01", "output stays zero-padded"


def rejects(*args):
    try:
        shift_civil_date(*args)
    except ValueError:
        return True
    return False


assert rejects("2023-02-29", 1), "Feb 29 off leap is rejected"
assert rejects("2024-13-01", 1), "month 13 is rejected"
assert rejects("2024-04-31", 0), "April 31 is rejected"
assert rejects("2024-1-05", 1), "unpadded month is rejected"
assert rejects("2024-06-15", 1.5), "fractional days is rejected"
assert rejects("9999-12-31", 1), "result past 9999 is rejected"
print("ok")
