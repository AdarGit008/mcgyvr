from solution import window_quota

assert window_quota(2, 10, []) == [], "no calls, no labels"
assert window_quota(2, 10, [[0, "a"], [1, "a"], [2, "a"]]) == [
    "ok",
    "ok",
    "over",
], "the third call in a frame is turned away"
assert window_quota(
    2, 10, [[0, "a"], [1, "a"], [2, "b"], [3, "b"], [4, "a"]]
) == ["ok", "ok", "ok", "ok", "over"], "names are metered separately"
assert window_quota(2, 10, [[8, "a"], [9, "a"], [10, "a"]]) == [
    "ok",
    "ok",
    "ok",
], "tick 10 opens a fresh frame"
assert window_quota(
    1, 5, [[0, "a"], [4, "a"], [5, "a"], [9, "a"], [10, "a"]]
) == ["ok", "over", "ok", "over", "ok"], "limit one resets at every frame edge"
assert window_quota(1, 3, [[2, "a"], [2, "a"], [3, "b"], [3, "b"]]) == [
    "ok",
    "over",
    "ok",
    "over",
], "equal times share a frame"


def rejects(*args):
    try:
        window_quota(*args)
    except ValueError:
        return True
    return False


assert rejects(0, 10, []), "zero limit"
assert rejects(2, 0, []), "zero width"
assert rejects(2, 10, [[0, ""]]), "empty name"
assert rejects(2, 10, [[-1, "a"]]), "negative time"
assert rejects(2, 10, [[True, "a"]]), "boolean time"
assert rejects(2, 10, [[5, "a"], [4, "a"]]), "time earlier than its predecessor"
print("ok")
