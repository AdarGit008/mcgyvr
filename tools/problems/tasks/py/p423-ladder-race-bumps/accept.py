from solution import race_ladder_board


def rejects(*args):
    try:
        race_ladder_board(*args)
    except ValueError:
        return True
    return False


assert race_ladder_board(6, [], [["x", 2], ["x", 3]]) == {"x": 5}, "one runner, two turns"
assert race_ladder_board(6, [], [["x", 5], ["x", 3], ["x", 1]]) == {
    "x": 6
}, "a forfeit turn leaves the runner in place"
assert race_ladder_board(5, [], [["z", 9]]) == {"z": 0}, "a runner may never leave square 0"
assert race_ladder_board(8, [], [["a", 4], ["b", 4]]) == {
    "a": 0,
    "b": 4,
}, "arriving knocks the sitter back"
assert race_ladder_board(7, [], [["a", 3], ["b", 3], ["a", 3]]) == {
    "a": 3,
    "b": 0,
}, "a knocked-back runner may return and knock back in turn"
assert race_ladder_board(10, [[2, 7]], [["a", 7], ["b", 2]]) == {
    "a": 0,
    "b": 7,
}, "a carried runner clears the exit square it rests on"
assert race_ladder_board(4, [], [["a", 4], ["a", 1]]) == {"a": 4}, "a home runner skips later turns"
assert race_ladder_board(9, [[4, 9]], [["a", 4], ["a", 2]]) == {
    "a": 9
}, "a chute may carry a runner home"
assert race_ladder_board(
    12,
    [[5, 9], [11, 3]],
    [["ana", 5], ["bo", 9], ["ana", 5], ["bo", 11], ["ana", 3], ["ana", 1], ["cy", 3]],
) == {"ana": 12, "bo": 0, "cy": 3}, "three runners over a lane with two chutes"

assert rejects(1, [], []), "a size under 2 is refused"
assert rejects(3.5, [], []), "a fractional size is refused"
assert rejects(8, [[3, 3]], []), "a mouth equal to its exit is refused"
assert rejects(8, [[8, 2]], []), "a mouth on the home square is refused"
assert rejects(9, [[3, 5], [3, 6]], []), "two chutes sharing a mouth are refused"
assert rejects(9, [[3, 5], [5, 7]], []), "an exit that is a mouth is refused"
assert rejects(9, [[3, 20]], []), "a chute square off the lane is refused"
assert rejects(9, [], [["a"]]), "a turn that is not a pair is refused"
assert rejects(9, [], [["", 2]]), "an empty name is refused"
assert rejects(9, [], [[7, 2]]), "a non-string name is refused"
assert rejects(9, [], [["a", 0]]), "steps of zero are refused"
assert rejects(9, [], [["a", 1.5]]), "fractional steps are refused"
print("ok")
