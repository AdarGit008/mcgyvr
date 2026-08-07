from solution import expand_nth_weekday

assert expand_nth_weekday(1, 0, "2000-01", 2) == [
    "2000-01-03",
    "2000-02-07",
], "first Mondays of Jan and Feb 2000"
assert expand_nth_weekday(-1, 6, "2000-02", 1) == [
    "2000-02-27"
], "final Sunday of leap February 2000"
assert expand_nth_weekday(5, 5, "2000-01", 3) == [
    "2000-01-29"
], "only January has a fifth Saturday"
assert expand_nth_weekday(-1, 4, "2026-08", 1) == [
    "2026-08-28"
], "final Friday of August 2026"
assert expand_nth_weekday(-1, 0, "2024-02", 1) == [
    "2024-02-26"
], "final Monday of leap February 2024"
assert expand_nth_weekday(1, 6, "1999-12", 2) == [
    "1999-12-05",
    "2000-01-02",
], "the span crosses a year boundary"
assert expand_nth_weekday(2, 2, "2026-08", 1) == [
    "2026-08-12"
], "second Wednesday of August 2026"


def rejects(*args):
    try:
        expand_nth_weekday(*args)
    except ValueError:
        return True
    return False


assert rejects(0, 0, "2000-01", 1), "ordinal zero"
assert rejects(6, 0, "2000-01", 1), "ordinal six"
assert rejects(1, 7, "2000-01", 1), "weekday seven"
assert rejects(1, 0, "2000-1", 1), "unpadded month"
assert rejects(1, 0, "2000-13", 1), "month thirteen"
assert rejects(1, 0, "2000-01", 0), "zero months"
assert rejects(1, 0, "2000-01", 241), "months beyond cap"
assert rejects(1, 0, "9999-12", 2), "span past 9999"
print("ok")
