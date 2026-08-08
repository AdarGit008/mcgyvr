from solution import weekday_name

assert weekday_name(2024, 1, 1) == "Monday", "January date is correct"
assert weekday_name(2024, 2, 29) == "Thursday", "leap-day February is correct"
assert weekday_name(2000, 1, 1) == "Saturday", "century January is correct"
assert weekday_name(2023, 3, 15) == "Wednesday", "March stays correct"
assert weekday_name(1999, 12, 31) == "Friday", "December stays correct"
assert weekday_name(1776, 7, 4) == "Thursday", "eighteenth-century date"
assert weekday_name(2026, 8, 7) == "Friday", "August date stays correct"


def rejects(*args):
    try:
        weekday_name(*args)
    except ValueError:
        return True
    return False


assert rejects(2024, 13, 1), "month 13 is rejected"
assert rejects(2023, 2, 29), "Feb 29 in a common year is rejected"
assert rejects(2024, 0, 10), "month 0 is rejected"
assert rejects(2024, 4, 31), "April 31 is rejected"
assert rejects(0, 5, 5), "year 0 is rejected"
assert rejects(2024, 1.5, 1), "fractional month is rejected"
print("ok")
