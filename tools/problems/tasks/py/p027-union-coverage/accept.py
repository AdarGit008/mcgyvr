from solution import union_coverage

assert union_coverage([[0, 0, 4, 3]]) == 12, "single rectangle"
assert union_coverage([[0, 0, 2, 2], [5, 5, 7, 8]]) == 10, "disjoint pair sums"
assert union_coverage([[0, 0, 2, 2], [0, 0, 2, 2]]) == 4, "duplicate counted once"
assert union_coverage([[0, 0, 3, 3], [1, 1, 4, 4]]) == 14, "partial overlap once"
assert union_coverage([[0, 0, 10, 10], [2, 2, 5, 5]]) == 100, "containment adds nothing"
assert union_coverage([[0, 3, 9, 6], [3, 0, 6, 9]]) == 45, "crossing strips"
assert union_coverage([[-2, -2, 0, 0], [-1, -1, 1, 1]]) == 7, "negative coordinates"
assert union_coverage([[0, 0, 1, 1], [1, 0, 2, 1]]) == 2, "edge-adjacent, no overlap"
assert union_coverage([]) == 0, "empty list covers nothing"


def rejects(value):
    try:
        union_coverage(value)
    except ValueError:
        return True
    return False


assert rejects([[0, 0, 0, 5]]), "zero width is rejected"
assert rejects([[2, 0, 1, 3]]), "reversed corners are rejected"
assert rejects([[0, 0, 1.5, 1]]), "fractional corner is rejected"
assert rejects([[0, 0, 1]]), "three-number entry is rejected"
assert rejects([[0, 0, 20001, 1]]), "out-of-range is rejected"
print("ok")
