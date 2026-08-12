from solution import plot_overlap

assert plot_overlap([0, 0, 4, 4], [2, 1, 6, 5]) == 6, "partial overlap"
assert plot_overlap([0, 0, 10, 10], [2, 3, 5, 7]) == 12, "a contained plot"
assert plot_overlap([0, 0, 4, 3], [0, 0, 4, 3]) == 12, "identical plots share everything"
assert plot_overlap([0, 0, 2, 2], [5, 5, 8, 8]) == 0, "disjoint plots share nothing"
assert plot_overlap([0, 0, 2, 2], [2, 0, 4, 2]) == 0, "an edge touch shares nothing"
assert plot_overlap([-3, -2, 1, 2], [-1, -1, 4, 1]) == 4, "negative edges"


def rejects(a, b):
    try:
        plot_overlap(a, b)
    except Exception:
        return True
    return False


assert rejects([0, 0, 2], [0, 0, 1, 1]), "three entries are rejected"
assert rejects([0, 0, 2.5, 2], [0, 0, 1, 1]), "a fractional edge is rejected"
assert rejects([3, 0, 1, 2], [0, 0, 1, 1]), "left at or past right is rejected"
print("ok")
