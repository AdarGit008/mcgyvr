from solution import crossing_point

assert crossing_point([[0, 0], [4, 4]], [[0, 4], [4, 0]]) == {
    "kind": "point",
    "x": [2, 1],
    "y": [2, 1],
}, "a plain crossing lands on the grid"

assert crossing_point([[0, 0], [2, 1]], [[0, 1], [2, 0]]) == {
    "kind": "point",
    "x": [1, 1],
    "y": [1, 2],
}, "a meeting halfway up is reported as a top over a bottom"

assert crossing_point([[-3, 0], [0, 1]], [[-1, -2], [-1, 5]]) == {
    "kind": "point",
    "x": [-1, 1],
    "y": [2, 3],
}, "thirds and a negative coordinate stay exact"

assert crossing_point([[-1, -1], [1, 1]], [[-1, 0], [1, 0]]) == {
    "kind": "point",
    "x": [0, 1],
    "y": [0, 1],
}, "a meeting at the origin has bottom one"

assert crossing_point([[0, 0], [2, 0]], [[2, 0], [2, 3]]) == {
    "kind": "point",
    "x": [2, 1],
    "y": [0, 1],
}, "strokes meeting only at an end still meet"

assert crossing_point([[0, 0], [2, 0]], [[0, 1], [2, 1]]) == {
    "kind": "apart"
}, "parallel strokes never meet"

assert crossing_point([[0, 0], [1, 0]], [[2, -1], [2, 1]]) == {
    "kind": "apart"
}, "the lines would meet but the strokes stop short"

assert crossing_point([[0, 0], [4, 0]], [[6, 0], [2, 0]]) == {
    "kind": "stretch",
    "from": [2, 0],
    "to": [4, 0],
}, "an overlap is reported from the smaller end"

assert crossing_point([[0, 0], [6, 3]], [[4, 2], [2, 1]]) == {
    "kind": "stretch",
    "from": [2, 1],
    "to": [4, 2],
}, "one stroke swallowed by the other gives the swallowed stretch"

assert crossing_point([[0, 0], [2, 2]], [[2, 2], [5, 5]]) == {
    "kind": "point",
    "x": [2, 1],
    "y": [2, 1],
}, "collinear strokes touching at one end share a single spot"

assert crossing_point([[0, 0], [1, 1]], [[3, 3], [5, 5]]) == {
    "kind": "apart"
}, "collinear strokes with a gap between them"


def rejects(*args):
    try:
        crossing_point(*args)
    except ValueError:
        return True
    return False


assert rejects(
    [[0, 0], [1, 1], [2, 2]], [[0, 1], [1, 0]]
), "three ends is not a stroke"
assert rejects([[0, 0], [0, 0]], [[0, 1], [1, 0]]), "a stroke of no length is rejected"
assert rejects(
    [[0, 0], [1, 0.5]], [[0, 1], [1, 0]]
), "a fractional coordinate is rejected"
assert rejects(
    [[0, 0], [1001, 0]], [[0, 1], [1, 0]]
), "an oversized coordinate is rejected"
assert rejects("line", [[0, 1], [1, 0]]), "a non-list stroke is rejected"
print("ok")
