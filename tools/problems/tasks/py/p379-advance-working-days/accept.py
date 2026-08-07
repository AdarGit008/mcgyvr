from solution import advance_working_days

assert advance_working_days("2024-03-04", 1, []) == "2024-03-05", "one day on from a Monday"
assert advance_working_days("2024-03-08", 1, []) == "2024-03-11", "one day on from a Friday clears the weekend"
assert advance_working_days("2024-03-04", 5, []) == "2024-03-11", "five working days on is a week"
assert advance_working_days("2024-03-04", 20, []) == "2024-04-01", "twenty working days on is four weeks"
assert advance_working_days("2024-03-04", 0, []) == "2024-03-04", "nought on a working day stays put"
assert advance_working_days("2024-03-08", 0, []) == "2024-03-08", "nought on a Friday stays put"
assert advance_working_days("2024-03-09", 0, []) == "2024-03-11", "nought on a Saturday rolls to the Monday"
assert (
    advance_working_days("2024-03-04", 0, ["2024-03-04", "2024-03-05"]) == "2024-03-06"
), "nought rolls over a run of shut days"
assert (
    advance_working_days("2024-03-10", 0, ["2024-03-11", "2024-03-12"]) == "2024-03-13"
), "nought on a Sunday rolls past the shut days behind it"
assert advance_working_days("2024-03-11", -1, []) == "2024-03-08", "one day back from a Monday"
assert advance_working_days("2024-03-11", -3, []) == "2024-03-06", "three days back"
assert advance_working_days("2024-03-04", -1, []) == "2024-03-01", "one day back over a weekend"
assert advance_working_days("2024-03-04", 3, ["2024-03-06"]) == "2024-03-08", "a shut day in the middle is stepped over"
assert advance_working_days("2024-03-09", 1, []) == "2024-03-11", "setting off from a Saturday still moves one working day"
assert advance_working_days("2024-03-09", -1, []) == "2024-03-08", "and one working day back from a Saturday"
assert advance_working_days("2024-02-28", 1, []) == "2024-02-29", "the leap day is a working day"
assert advance_working_days("2023-02-28", 1, []) == "2023-03-01", "a plain February has no 29th to land on"
assert advance_working_days("2024-12-31", 1, []) == "2025-01-01", "a step across the turn of the year"
assert advance_working_days("2024-01-01", 250, []) == "2024-12-16", "a long walk through a leap year"


def rejects(start, count, closures):
    try:
        advance_working_days(start, count, closures)
    except ValueError:
        return True
    return False


assert rejects("2024-03-04", 5001, []), "a move past five thousand is refused"
assert rejects("2024-03-04", -5001, []), "and past minus five thousand"
assert rejects("2024-03-04", 1.5, []), "a fractional move is refused"
assert rejects("2024-3-04", 1, []), "a date that is not zero-padded is refused"
assert rejects("2023-02-29", 1, []), "the 29th of a plain February is refused"
assert rejects("2024-03-04", 1, ["2024-03-06", "2024-03-06"]), "a shut day named twice is refused"
assert rejects("2024-03-04", 1, ["nope"]), "a malformed shut day is refused"
assert rejects("2999-12-31", 5000, []), "a walk off the far end is refused"
assert rejects("1900-01-01", -5000, []), "a walk off the near end is refused"
print("ok")
