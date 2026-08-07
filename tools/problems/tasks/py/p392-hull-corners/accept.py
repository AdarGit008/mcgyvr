from solution import hull_corners

assert hull_corners([[0, 0], [2, 0], [2, 2], [0, 2]]) == [
    [0, 0],
    [2, 0],
    [2, 2],
    [0, 2],
], "a square keeps its four posts, counter-clockwise from the least corner"

assert hull_corners([[1, 0], [0, 2], [2, 2], [1, 1], [0, 0], [2, 0]]) == [
    [0, 0],
    [2, 0],
    [2, 2],
    [0, 2],
], "a post flat on a run and a marker inside are both left out"

assert hull_corners([[-2, -2], [2, -2], [2, 2], [-2, 2], [0, 0], [-2, -2]]) == [
    [-2, -2],
    [2, -2],
    [2, 2],
    [-2, 2],
], "negative coordinates and a repeat change nothing"

assert hull_corners([[0, 0], [4, 0], [0, 3]]) == [
    [0, 0],
    [4, 0],
    [0, 3],
], "a triangle already given counter-clockwise"

assert hull_corners([[0, 3], [4, 0], [0, 0]]) == [
    [0, 0],
    [4, 0],
    [0, 3],
], "the same triangle given the other way round"

assert hull_corners([[3, 3], [3, 3], [3, 3]]) == [
    [3, 3]
], "one shared spot collapses to that spot"

assert hull_corners([[2, 4], [-1, -2], [1, 2], [0, 0]]) == [
    [-1, -2],
    [2, 4],
], "a straight run collapses to its two far ends"

assert hull_corners([[7, -5]]) == [[7, -5]], "one marker is one post"

assert hull_corners([[0, 0], [0, 5], [0, 2]]) == [
    [0, 0],
    [0, 5],
], "a vertical run keeps only its ends"


def rejects(*args):
    try:
        hull_corners(*args)
    except ValueError:
        return True
    return False


assert rejects([]), "an empty list is rejected"
assert rejects("points"), "a non-list is rejected"
assert rejects([[1, 2, 3]]), "a triple is not a marker"
assert rejects([[1, 1.5]]), "a fractional coordinate is rejected"
assert rejects([[0, 0], [2000000, 1]]), "an oversized coordinate is rejected"
print("ok")
