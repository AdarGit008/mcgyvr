from solution import drain_lanes

assert drain_lanes([["only", 2]], [["x", "only"], ["y", "only"], ["z", "only"]]) == {
    "order": ["x", "y", "z"],
    "rounds": 2,
}, "one lane drains in arrival order"
assert drain_lanes(
    [["express", 1], ["bulk", 1]],
    [["e1", "express"], ["e2", "express"], ["b1", "bulk"]],
) == {"order": ["e1", "b1", "e2"], "rounds": 2}, "lanes alternate in plan order"
assert drain_lanes(
    [["a", 2], ["b", 1]],
    [["a1", "a"], ["a2", "a"], ["a3", "a"], ["b1", "b"], ["b2", "b"]],
) == {
    "order": ["a1", "a2", "b1", "a3", "b2"],
    "rounds": 2,
}, "a quota takes several labels per visit"
assert drain_lanes(
    [["a", 1], ["b", 1]], [["a1", "a"], ["b1", "b"], ["b2", "b"], ["b3", "b"]]
) == {
    "order": ["a1", "b1", "b2", "b3"],
    "rounds": 3,
}, "an exhausted lane never strands the others"
assert drain_lanes([["a", 3]], [["a1", "a"], ["a2", "a"]]) == {
    "order": ["a1", "a2"],
    "rounds": 1,
}, "a short take drains what is there"
assert drain_lanes([["a", 1], ["b", 2]], [["b1", "b"], ["b2", "b"]]) == {
    "order": ["b1", "b2"],
    "rounds": 1,
}, "a lane that never held items is skipped over"
assert drain_lanes([["a", 1]], []) == {"order": [], "rounds": 0}, "nothing to drain"


def rejects(plan, items):
    try:
        drain_lanes(plan, items)
    except ValueError:
        return True
    return False


assert rejects([], []), "empty plan is rejected"
assert rejects([["a", 0]], []), "zero quota is rejected"
assert rejects([["a", 1.5]], []), "fractional quota is rejected"
assert rejects([["a", 1], ["a", 2]], []), "duplicate lane is rejected"
assert rejects([["", 1]], []), "empty lane name is rejected"
assert rejects([["a"]], []), "lone plan entry is rejected"
assert rejects([["a", 1]], [["solo"]]), "lone item is rejected"
assert rejects([["a", 1]], [[7, "a"]]), "non-string label is rejected"
assert rejects([["a", 1]], [["x", "ghost"]]), "undeclared lane is rejected"
print("ok")
