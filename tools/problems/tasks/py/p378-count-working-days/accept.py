from solution import count_working_days

assert count_working_days("2024-03-04", "2024-03-08", [5, 6], []) == 5, "a plain Monday-to-Friday week"
assert count_working_days("2024-03-04", "2024-03-10", [5, 6], []) == 5, "the two closed days drop out"
assert count_working_days("2024-03-04", "2024-03-10", [], []) == 7, "an empty weekend leaves every day worked"
assert count_working_days("2024-03-04", "2024-03-08", [5, 6], ["2024-03-06"]) == 4, "a shut date inside the span"
assert (
    count_working_days("2024-03-04", "2024-03-08", [5, 6], ["2024-03-15"]) == 5
), "a shut date outside the span is passed over"
assert (
    count_working_days("2024-03-04", "2024-03-10", [5, 6], ["2024-03-09"]) == 5
), "a shut date on a closed day is not deducted twice"
assert count_working_days("2024-03-09", "2024-03-09", [5, 6], []) == 0, "one closed day alone works nothing"
assert count_working_days("2024-03-08", "2024-03-08", [5, 6], []) == 1, "one open day alone works one"
assert count_working_days("2024-02-01", "2024-02-29", [5, 6], []) == 21, "a leap February"
assert count_working_days("2023-02-01", "2023-02-28", [5, 6], []) == 20, "the same month a year earlier"
assert (
    count_working_days("2024-03-01", "2024-03-31", [0, 1, 2, 3, 4, 5], []) == 5
), "six closed days leave only the Sundays"
assert count_working_days("2024-01-01", "2024-12-31", [5, 6], []) == 262, "a whole leap year"
assert (
    count_working_days("2024-03-04", "2024-03-08", [5, 6], ["2024-03-05", "2024-03-07"]) == 3
), "two shut dates in one week"
assert count_working_days("1900-01-01", "1900-01-31", [5, 6], []) == 23, "a month at the low end of the range"
assert (
    count_working_days("2024-12-30", "2025-01-03", [5, 6], ["2025-01-01"]) == 4
), "a span crossing the turn of the year"


def rejects(opening, closing, weekend, holidays):
    try:
        count_working_days(opening, closing, weekend, holidays)
    except ValueError:
        return True
    return False


assert rejects("2024-03-08", "2024-03-04", [5, 6], []), "a closing date behind the opening one is refused"
assert rejects("2024-3-08", "2024-03-04", [5, 6], []), "a date that is not zero-padded is refused"
assert rejects("2023-02-29", "2023-03-01", [5, 6], []), "the 29th of a plain February is refused"
assert rejects("1899-12-31", "1900-01-01", [5, 6], []), "a year below 1900 is refused"
assert rejects("2024-13-01", "2024-13-02", [5, 6], []), "a month above 12 is refused"
assert rejects("2024-03-04", "2024-03-08", [5, 5], []), "a weekend naming a day twice is refused"
assert rejects("2024-03-04", "2024-03-08", [0, 1, 2, 3, 4, 5, 6], []), "a weekend of all seven days is refused"
assert rejects("2024-03-04", "2024-03-08", [7], []), "a weekday number above 6 is refused"
assert (
    rejects("2024-03-04", "2024-03-08", [5, 6], ["2024-03-05", "2024-03-05"])
), "a shut date named twice is refused"
assert rejects("2024-03-04", "2024-03-08", [5, 6], ["not-a-date"]), "a malformed shut date is refused"
assert rejects("1900-01-01", "2999-12-31", [5, 6], []), "a span longer than forty thousand days is refused"
print("ok")
