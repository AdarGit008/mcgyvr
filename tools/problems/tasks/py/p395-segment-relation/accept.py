from solution import segment_relation

assert (
    segment_relation([[0, 0], [4, 4]], [[0, 4], [4, 0]]) == "pinned"
), "a crossing on a graph-paper corner"

assert (
    segment_relation([[0, 0], [2, 1]], [[0, 1], [2, 0]]) == "adrift"
), "a meeting halfway up a square is between crossings"

assert (
    segment_relation([[0, 0], [3, 3]], [[0, 1], [3, 0]]) == "adrift"
), "three quarters along is between crossings too"

assert (
    segment_relation([[0, 0], [4, 0]], [[2, 0], [2, 5]]) == "pinned"
), "a tip planted on the middle of the other rod"

assert (
    segment_relation([[0, 0], [2, 0]], [[0, 3], [2, 3]]) == "clear"
), "rods that never converge"

assert (
    segment_relation([[0, 0], [1, 0]], [[3, -2], [3, 2]]) == "clear"
), "the lines would converge past the ends of the rods"

assert (
    segment_relation([[-4, -2], [4, 2]], [[0, 0], [8, 4]]) == "shared"
), "a common length along one line"

assert (
    segment_relation([[0, 0], [2, 2]], [[2, 2], [7, 7]]) == "pinned"
), "same line, meeting at one tip only"

assert (
    segment_relation([[0, 0], [1, 1]], [[4, 4], [6, 6]]) == "clear"
), "same line but a gap between the rods"

assert (
    segment_relation([[-3, -3], [-1, -1]], [[-3, -1], [-1, -3]]) == "pinned"
), "negative measures cross on a corner"


def rejects(*args):
    try:
        segment_relation(*args)
    except ValueError:
        return True
    return False


assert rejects([[0, 0]], [[0, 1], [1, 0]]), "one tip is not a rod"
assert rejects([[3, 3], [3, 3]], [[0, 1], [1, 0]]), "coincident tips are rejected"
assert rejects([[0, 0], [1, None]], [[0, 1], [1, 0]]), "a missing measure is rejected"
assert rejects([[0, 0], [501, 0]], [[0, 1], [1, 0]]), "an oversized measure is rejected"
assert rejects(None, [[0, 1], [1, 0]]), "a missing rod is rejected"
print("ok")
