from solution import aged_service_order


def join(tick, who, rank):
    return {"kind": "join", "tick": tick, "who": who, "rank": rank}


def call(tick):
    return {"kind": "call", "tick": tick}


def rejects(events, step):
    try:
        aged_service_order(events, step)
    except ValueError:
        return True
    return False


assert aged_service_order([join(0, "a", 1), join(0, "b", 3), call(1)], 5) == [
    "b"
], "with no aging yet the higher rank goes first"

assert aged_service_order([join(0, "old", 1), join(9, "new", 2), call(10)], 5) == [
    "old"
], "two aging steps lift the long waiter past a fresher caller"

assert aged_service_order([join(0, "old", 1), join(4, "new", 2), call(4)], 5) == [
    "new"
], "before a whole step passes the rank still decides"

assert aged_service_order([join(0, "alpha", 0), join(5, "beta", 1), call(5)], 5) == [
    "alpha"
], "level standing goes to the earlier join tick"

assert aged_service_order([join(0, "zeta", 2), join(0, "beta", 2), call(0)], 5) == [
    "beta"
], "level standing and equal join ticks go to the earlier name"

assert aged_service_order(
    [join(0, "p", 0), join(0, "q", 4), join(1, "r", 2), call(1), call(7), call(7)], 3
) == ["q", "r", "p"], "standings are recomputed at every call"

assert aged_service_order(
    [join(0, "a", 1), call(0), join(1, "b", 0), join(2, "c", 0), call(9), call(9)], 4
) == ["a", "b", "c"], "callers joining after a call age from their own join tick"

assert aged_service_order(
    [join(0, "x", 1), call(0), join(1, "x", 1), call(1)], 5
) == ["x", "x"], "a name freed by a call may join again"

assert rejects([join(0, "a", 1), call(0)], 0), "a step of zero is rejected"
assert rejects([], 5), "an empty log is rejected"
assert rejects([{"kind": "leave", "tick": 0}], 5), "an unknown kind is rejected"
assert rejects([join(-1, "a", 1)], 5), "a negative tick is rejected"
assert rejects([join(5, "a", 1), call(2)], 5), "a tick running backwards is rejected"
assert rejects([join(0, "", 1)], 5), "a joining caller with no name is rejected"
assert rejects([join(0, "a", -1)], 5), "a negative rank is rejected"
assert rejects(
    [join(0, "a", 1), join(1, "a", 2)], 5
), "a name already waiting cannot join again"
assert rejects([call(0)], 5), "a call on an empty waiting room is rejected"

print("ok")
