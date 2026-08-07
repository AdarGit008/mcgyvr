from solution import trace_teleports

assert trace_teleports([1, 2, 3, 1], 0) == [1, 3, 1], "one ride to a 3-circuit"
assert trace_teleports([1, 2, 3, 1], 2) == [0, 3, 2], "starting on the circuit"
assert trace_teleports([0], 0) == [0, 1, 0], "a pad wired to itself"
assert trace_teleports([1, 1], 0) == [1, 1, 1], "tail into a self-wired pad"
assert trace_teleports([3, 0, 1, 2], 0) == [0, 4, 0], "the whole hall circles"
assert trace_teleports([1, 2, 0, 2], 3) == [1, 3, 2], "side pad feeds the ring"


def rejects(pads, start):
    try:
        trace_teleports(pads, start)
    except ValueError:
        return True
    return False


assert rejects([], 0), "empty hall is rejected"
assert rejects([2], 0), "destination outside the hall"
assert rejects([0, 1], 5), "start outside the hall"
print("ok")
