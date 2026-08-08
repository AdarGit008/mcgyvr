from solution import meridian_week_label

assert meridian_week_label("2026-01-07") == "2026-W01", "a week opening on the seventh holds the eighth"
assert meridian_week_label("2026-01-13") == "2026-W01", "the closing Tuesday of week one"
assert meridian_week_label("2026-01-14") == "2026-W02", "the next Wednesday opens week two"
assert meridian_week_label("2026-01-06") == "2025-W52", "the day before week one falls back a year"
assert meridian_week_label("2025-12-31") == "2025-W52", "the tail of December keeps its own year"
assert meridian_week_label("2025-01-01") == "2024-W53", "2024 is a fifty-three week Meridian year"
assert meridian_week_label("2024-02-29") == "2024-W09", "a leap day lands in week nine"
assert meridian_week_label("2027-01-04") == "2026-W52", "a week may spill into the next January"
assert meridian_week_label("2026-12-30") == "2026-W52", "that same spilling week opens in December"
assert meridian_week_label("2020-12-31") == "2020-W52", "an ordinary year closes at week fifty-two"
assert meridian_week_label("2000-01-01") == "1999-W52", "the century turn falls back a year"
assert meridian_week_label("9999-12-31") == "9999-W52", "the top of the permitted span"


def rejects(value):
    try:
        meridian_week_label(value)
    except ValueError:
        return True
    return False


assert rejects("2026-1-07"), "an unpadded month is rejected"
assert rejects("2026-01-07 "), "a trailing space is rejected"
assert rejects("0001-06-01"), "a year below the span is rejected"
assert rejects("2026-13-01"), "a month above twelve is rejected"
assert rejects("2026-00-05"), "a month of zero is rejected"
assert rejects("2025-02-29"), "February 29 of a common year is rejected"
assert rejects("2026-04-31"), "a thirty-first of April is rejected"
assert rejects(20260107), "a non-text argument is rejected"
print("ok")
