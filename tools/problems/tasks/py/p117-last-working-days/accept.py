from solution import last_working_days

assert last_working_days("2026-01", 5) == [
    "2026-01-30",
    "2026-02-27",
    "2026-03-31",
    "2026-04-30",
    "2026-05-29",
], "early 2026, including a Saturday close and a Sunday close"
assert last_working_days("2023-12", 1) == [
    "2023-12-29"
], "December 2023 closes on a Sunday"
assert last_working_days("2023-04", 1) == [
    "2023-04-28"
], "April 2023 also closes on a Sunday"
assert last_working_days("2023-09", 1) == [
    "2023-09-29"
], "September 2023 closes on a Saturday"
assert last_working_days("2024-02", 1) == [
    "2024-02-29"
], "leap February 2024 closes on a Thursday"
assert last_working_days("1999-12", 2) == [
    "1999-12-31",
    "2000-01-31",
], "a run across the millennium boundary"


def rejects(*args):
    try:
        last_working_days(*args)
    except ValueError:
        return True
    return False


assert rejects("2024-2", 1), "unpadded month"
assert rejects("2024-00", 1), "month zero"
assert rejects("2024-01", 0), "zero count"
assert rejects("2024-01", 121), "count beyond cap"
assert rejects("9999-12", 2), "run past 9999"
print("ok")
