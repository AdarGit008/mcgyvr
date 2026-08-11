from solution import replay_buffer

assert replay_buffer(["add:a", "add:b", "take"], 2) == {
    "held": ["b"],
    "taken": ["a"],
}, "a take removes the oldest entry"
assert replay_buffer([], 3) == {
    "held": [],
    "taken": [],
}, "no operations leave an empty result"
assert replay_buffer(["add:a", "take", "add:b", "add:c"], 2) == {
    "held": ["b", "c"],
    "taken": ["a"],
}, "interleaved adds and takes"
assert replay_buffer(["add:x", "add:y", "take", "add:z"], 2) == {
    "held": ["y", "z"],
    "taken": ["x"],
}, "a take frees a slot"


def rejects(ops, capacity):
    try:
        replay_buffer(ops, capacity)
    except ValueError:
        return True
    return False


assert rejects(["add:a", "add:b", "add:c"], 2), "an add on a full buffer is an error"
assert rejects(["take"], 1), "a take on an empty buffer is an error"
assert rejects(["drop:a"], 1), "an unknown operation is an error"
assert rejects([], 0), "zero capacity is rejected"
assert rejects([], 2.5), "fractional capacity is rejected"
print("ok")
