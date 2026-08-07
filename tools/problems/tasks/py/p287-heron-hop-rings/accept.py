from solution import reach_by_hops

assert reach_by_hops(1, 1, [0, 0], [], 0) == [1], (
    "no hops at all still counts the standing square"
)
assert reach_by_hops(1, 1, [0, 0], [], 3) == [1, 0, 0, 0], (
    "a fen of one square leaves every later ring empty"
)
assert reach_by_hops(5, 5, [0, 0], [], 1) == [1, 4], (
    "a corner offers a short and a long hop each way"
)
assert reach_by_hops(5, 5, [0, 0], [], 2) == [1, 4, 8], (
    "the second ring off the corner"
)
assert reach_by_hops(3, 3, [1, 1], [], 2) == [1, 4, 4], (
    "a small fen fills in two rings"
)
assert reach_by_hops(6, 1, [0, 0], [], 2) == [1, 2, 2], (
    "one row deep, hopping along the line"
)
assert reach_by_hops(4, 4, [3, 3], [], 3) == [1, 4, 6, 4], (
    "starting at the far corner needs the hop back toward the top"
)
assert reach_by_hops(4, 4, [0, 0], [[0, 1], [1, 0]], 1) == [1, 2], (
    "marsh beside the start closes both short hops"
)
assert reach_by_hops(4, 4, [0, 0], [[0, 1], [1, 0]], 2) == [1, 2, 5], (
    "the fen still opens up once the long hops are taken"
)


def rejects(across, down, start, marsh, hops):
    try:
        reach_by_hops(across, down, start, marsh, hops)
    except ValueError:
        return True
    return False


assert rejects(0, 3, [0, 0], [], 1), "a fen with no columns"
assert rejects(3, 2.5, [0, 0], [], 1), "a fractional depth"
assert rejects(3, 3, [0, 0], [], -1), "a negative hop budget"
assert rejects(3, 3, [0, 3], [], 1), "start off the fen"
assert rejects(3, 3, [0, 0], [[0, 0]], 1), "start standing in marsh"
assert rejects(3, 3, [0, 0], [[9, 0]], 1), "marsh off the fen"
assert rejects(3, 3, [0, 0], [[1, 1], [1, 1]], 1), "the same marsh square twice"
assert rejects(3, 3, [0, 0], "wet", 1), "marsh is not a list"
assert rejects(3, 3, [0], [], 1), "start is not a pair"
print("ok")
