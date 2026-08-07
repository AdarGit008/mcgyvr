from solution import deal_packet

assert deal_packet(["a", "b", "c", "d", "e"], [2, 2], "round") == {
    "hands": [["a", "c"], ["b", "d"]],
    "left": ["e"],
}, "what will not fit becomes the leavings"
assert deal_packet(["a", "b", "c", "d", "e", "f"], [3, 1, 2], "round") == {
    "hands": [["a", "d", "f"], ["b"], ["c", "e"]],
    "left": [],
}, "a hand at its limit is passed over"
assert deal_packet(["a", "b", "c", "d", "e", "f", "g"], [2, 2, 2], "snake") == {
    "hands": [["a", "f"], ["b", "e"], ["c", "d"]],
    "left": ["g"],
}, "snake calls each end twice"
assert deal_packet(["a", "b", "c"], [1, 1], "reverse") == {
    "hands": [["b"], ["a"]],
    "left": ["c"],
}, "reverse opens with the last hand"
assert deal_packet([], [2], "round") == {
    "hands": [[]],
    "left": [],
}, "an empty packet leaves every hand empty"
assert deal_packet(["a", "b"], [3], "snake") == {
    "hands": [["a", "b"]],
    "left": [],
}, "one hand takes every call"
assert deal_packet(["a", "b", "c", "d"], [1, 1, 1], "snake") == {
    "hands": [["a"], ["b"], ["c"]],
    "left": ["d"],
}, "limits of one fill on the way up"
assert deal_packet(["a", "b", "c", "d", "e"], [4, 1], "reverse") == {
    "hands": [["b", "c", "d", "e"], ["a"]],
    "left": [],
}, "one full hand hands every later call to the other"


def rejects(items, seats, order):
    try:
        deal_packet(items, seats, order)
    except ValueError:
        return True
    return False


assert rejects("abc", [1], "round"), "a packet that is not a list is rejected"
assert rejects([""], [1], "round"), "an empty packet entry is rejected"
assert rejects([5], [1], "round"), "a non-string packet entry is rejected"
assert rejects(["a", "a"], [2], "round"), "a repeated packet entry is rejected"
assert rejects(["a"], 2, "round"), "limits that are not a list are rejected"
assert rejects(["a"], [], "round"), "an empty list of limits is rejected"
assert rejects(["a"], [0], "round"), "a limit of zero is rejected"
assert rejects(["a"], [1.5], "round"), "a fractional limit is rejected"
assert rejects(["a"], ["2"], "round"), "a limit that is not a number is rejected"
assert rejects(["a"], [1], "spiral"), "an unknown turn sequence is rejected"
assert rejects(["a"], [1], 3), "a turn sequence that is not a string is rejected"
print("ok")
