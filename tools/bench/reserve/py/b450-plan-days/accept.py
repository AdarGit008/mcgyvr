from solution import days_for, plan_days


def rejects(size, rate):
    try:
        days_for(size, rate)
    except Exception:
        return True
    return False


assert days_for(10, 5) == 2, "an exact number of days"
assert days_for(11, 5) == 3, "a part day counts as one"
assert days_for(0, 5) == 0, "no work, no days"
assert plan_days([10, 11], 5) == [2, 3], "a plan for two jobs"
assert plan_days([], 5) == [], "no jobs at all"
assert rejects(10, 0), "a rate of zero is rejected"
print("ok")
