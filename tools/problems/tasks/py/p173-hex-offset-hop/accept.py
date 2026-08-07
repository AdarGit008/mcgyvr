from solution import hop_offset_grid

assert hop_offset_grid([0, 0], ["se", "ne"]) == {
    "cell": [1, 0],
    "distance": 1,
}, "leaving the shifted row, northeast keeps the column climbing"
assert hop_offset_grid([0, 0], ["se", "nw"]) == {
    "cell": [0, 0],
    "distance": 0,
}, "southeast then northwest returns to the starting address"
assert hop_offset_grid([0, 0], ["se", "se"]) == {
    "cell": [1, 2],
    "distance": 2,
}, "two southeast moves cross a shifted row and gain a column"
assert hop_offset_grid([0, 0], ["sw", "sw"]) == {
    "cell": [-1, 2],
    "distance": 2,
}, "two southwest moves drop one column, not two"
assert hop_offset_grid([0, 0], ["nw", "nw"]) == {
    "cell": [-1, -2],
    "distance": 2,
}, "rows above the origin shift by the same parity rule"
assert hop_offset_grid([4, -3], ["ne", "ne"]) == {
    "cell": [5, -5],
    "distance": 2,
}, "a negative odd row shifts exactly as a positive odd row does"
assert hop_offset_grid([2, 3], ["e", "w", "ne", "sw"]) == {
    "cell": [2, 3],
    "distance": 0,
}, "a walk that returns home reports no distance at all"
assert hop_offset_grid([7, -2], []) == {
    "cell": [7, -2],
    "distance": 0,
}, "an empty move list ends where it began"
assert hop_offset_grid([0, 0], ["e", "e", "se"]) == {
    "cell": [2, 1],
    "distance": 3,
}, "three moves that never double back stay three apart"
assert hop_offset_grid([0, 0], ["w", "sw", "sw", "e"]) == {
    "cell": [-1, 2],
    "distance": 2,
}, "four moves can leave only two hops between the ends"


def rejects(start, moves):
    try:
        hop_offset_grid(start, moves)
    except ValueError:
        return True
    return False


assert rejects([0, 0], ["up"]), "an unknown move is rejected"
assert rejects([0, 0], ["NE"]), "an upper-case move is rejected"
assert rejects([0], ["e"]), "a one-element start is rejected"
assert rejects([0, 0.5], ["e"]), "a fractional row is rejected"
assert rejects("00", ["e"]), "a non-address start is rejected"
assert rejects([0, 0], "e"), "a non-list move list is rejected"
print("ok")
