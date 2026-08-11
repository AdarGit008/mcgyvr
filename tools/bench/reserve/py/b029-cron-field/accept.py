from solution import expand_cron_field

assert expand_cron_field("*", 1, 5) == [1, 2, 3, 4, 5], "star spans the bounds"
assert expand_cron_field("30", 0, 59) == [30], "single number"
assert expand_cron_field("3,1,2", 1, 5) == [1, 2, 3], "list comes back sorted"
assert expand_cron_field("10-13", 0, 59) == [10, 11, 12, 13], "range is inclusive"
assert expand_cron_field("*/15", 0, 59) == [0, 15, 30, 45], "star with a step"
assert expand_cron_field("2-11/3", 0, 59) == [2, 5, 8, 11], "range with a step"
assert expand_cron_field("1-3,2-4", 1, 10) == [1, 2, 3, 4], "overlap collapses"
assert expand_cron_field("0,20-22,*/30", 0, 59) == [0, 20, 21, 22, 30], "mixed items merge"


def rejects(field, low, high):
    try:
        expand_cron_field(field, low, high)
    except Exception:
        return True
    return False


assert rejects(42, 0, 59), "non-string field is rejected"
assert rejects("", 0, 59), "empty field is rejected"
assert rejects("1,", 0, 59), "empty item is rejected"
assert rejects("5-2", 0, 59), "reversed range is rejected"
assert rejects("*/0", 0, 59), "zero step is rejected"
assert rejects("5/2", 0, 59), "step on a single number is rejected"
assert rejects("61", 0, 59), "number above the bounds is rejected"
assert rejects("3-", 0, 59), "range missing its high end is rejected"
assert rejects("1-3x", 0, 59), "letters are rejected"
print("ok")
