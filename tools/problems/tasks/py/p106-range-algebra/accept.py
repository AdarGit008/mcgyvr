from solution import range_algebra

assert range_algebra([[0, 3]], [[3, 6]], "union") == [
    [0, 6]
], "touching pieces fuse across operands"
assert range_algebra([[8, 12], [1, 4]], [[3, 9]], "union") == [
    [1, 12]
], "union bridges through the middle"
assert range_algebra([[5, 9], [0, 2]], [], "union") == [
    [0, 2],
    [5, 9],
], "union with an empty operand canonicalises the other"
assert range_algebra([[0, 10]], [[2, 4], [6, 8]], "intersect") == [
    [2, 4],
    [6, 8],
], "intersection keeps only the shared integers"
assert range_algebra([[0, 3]], [[3, 6]], "intersect") == [], "touching sets share nothing"
assert range_algebra([[0, 5], [4, 9]], [[3, 7]], "intersect") == [
    [3, 7]
], "overlap inside one operand is flattened first"
assert range_algebra([[0, 10]], [[3, 5]], "subtract") == [
    [0, 3],
    [5, 10],
], "subtracting the middle splits a piece"
assert range_algebra([[2, 6]], [[0, 10]], "subtract") == [], "subtracting a superset leaves nothing"
assert range_algebra([[1, 4], [6, 9]], [[3, 7]], "subtract") == [
    [1, 3],
    [7, 9],
], "subtraction clips both sides"
assert range_algebra([[0, 4]], [[4, 8]], "subtract") == [
    [0, 4]
], "a touching subtrahend removes nothing"


def rejects(a, b, op):
    try:
        range_algebra(a, b, op)
    except ValueError:
        return True
    return False


assert rejects([], [], "xor"), "unknown op is rejected"
assert rejects([[3, 3]], [], "union"), "an empty interval is rejected"
assert rejects([[5, 2]], [], "union"), "a backwards interval is rejected"
assert rejects([[0, 1.5]], [], "union"), "a fractional endpoint is rejected"
assert rejects([[0, 1, 2]], [], "union"), "a triple is rejected"
print("ok")
