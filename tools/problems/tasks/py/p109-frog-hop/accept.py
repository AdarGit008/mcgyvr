from solution import can_hop

pond = [
    "F.G..",
    ".H...",
    "..F..",
    ".....",
    "...KK",
]

assert can_hop(pond, [2, 2], [2, 3]) is True, "a step sideways onto open water"
assert can_hop(pond, [2, 2], [1, 2]) is True, "a step upward"
assert can_hop(pond, [0, 2], [2, 0]) is True, "a diagonal vault over an occupied midpoint"
assert can_hop(pond, [4, 4], [4, 2]) is True, "a horizontal vault over a neighbour"
assert can_hop(pond, [4, 3], [4, 4]) is False, "the to square must be open water"
assert can_hop(pond, [3, 3], [3, 4]) is False, "the from square must be occupied"
assert can_hop(pond, [2, 2], [2, 4]) is False, "a vault needs its midpoint occupied"
assert can_hop(pond, [2, 2], [0, 2]) is False, "a vertical vault over open water fails"
assert can_hop(pond, [2, 2], [3, 3]) is False, "a one-square diagonal is not a step"
assert can_hop(pond, [0, 0], [0, 3]) is False, "three squares is out of reach"
assert can_hop(pond, [0, 0], [1, 2]) is False, "a knight-shaped move is neither shape"


def rejects(pond, origin, dest):
    try:
        can_hop(pond, origin, dest)
    except ValueError:
        return True
    return False


assert rejects(pond[1:], [0, 0], [0, 1]), "four rows are rejected"
assert rejects(
    ["F.G..", ".H...", "..F..", ".....", "...K"], [0, 0], [0, 1]
), "a short row is rejected"
assert rejects(pond, [0, 5], [0, 1]), "a coordinate above 4 is rejected"
assert rejects(pond, [0, 0], [0, 1.5]), "a fractional coordinate is rejected"
assert rejects(pond, [0], [0, 1]), "a one-number square is rejected"
print("ok")
