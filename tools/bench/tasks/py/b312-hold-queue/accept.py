from solution import hold_queue


def rejects(callers, limit):
    try:
        hold_queue(callers, limit)
    except Exception:
        return True
    return False


assert hold_queue(["a", "b", "c"], 2) == ["b", "c"], "the longest wait goes"
assert hold_queue(["a"], 2) == ["a"], "under the limit"
assert hold_queue([], 3) == [], "nobody called"
assert hold_queue(["a", "b", "c", "d"], 1) == ["d"], "only the newest survives"
assert hold_queue(["a", "b"], 5) == ["a", "b"], "a roomy limit"
assert rejects([], 0), "a limit of zero is rejected"
print("ok")
