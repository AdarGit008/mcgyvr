from solution import throttle_calls

assert throttle_calls([0, 1, 2], 5, 10) == [True, True, True], "under the limit every call passes"
assert throttle_calls([0, 1, 2], 2, 10) == [True, True, False], "the burst stops at the limit"
assert throttle_calls([0, 4], 1, 5) == [True, False], "a call still inside the window counts"
assert throttle_calls([0, 5], 1, 5) == [True, True], "a call exactly window later stops counting"
assert throttle_calls([0, 0, 1, 3], 2, 3) == [True, True, False, True], "expiry frees the quota again"
assert throttle_calls([0, 1, 2], 1, 2) == [True, False, True], "a refused call never counts later"
assert throttle_calls([], 3, 4) == [], "no calls yields no verdicts"


def rejects(times, limit, window):
    try:
        throttle_calls(times, limit, window)
    except Exception:
        return True
    return False


assert rejects("soon", 1, 1), "a non-list of arrivals is rejected"
assert rejects([0, 1.5], 1, 1), "a fractional arrival is rejected"
assert rejects([3, 1], 1, 1), "decreasing arrivals are rejected"
assert rejects([0], 0, 1), "a zero limit is rejected"
assert rejects([0], 1, 0), "a zero window is rejected"
print("ok")
