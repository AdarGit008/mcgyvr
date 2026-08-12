from solution import panel_coverage


def report(union, overlap, deepest, perimeter, bounds):
    return {
        "union": union,
        "overlap": overlap,
        "deepest": deepest,
        "perimeter": perimeter,
        "bounds": bounds,
    }


assert panel_coverage([]) == report(
    0, 0, 0, 0, None
), "no panels yields all zeros and null bounds"
assert panel_coverage([[0, 0, 3, 2]]) == report(
    6, 0, 1, 10, [0, 0, 3, 2]
), "a single panel is its own report"
assert panel_coverage([[0, 0, 1, 1], [2, 2, 3, 3]]) == report(
    2, 0, 1, 8, [0, 0, 3, 3]
), "disjoint panels add areas and perimeters"
assert panel_coverage([[0, 0, 2, 2], [2, 0, 4, 2]]) == report(
    8, 0, 1, 12, [0, 0, 4, 2]
), "touching panels share a seam, not ground or boundary"
assert panel_coverage([[0, 0, 2, 2], [1, 1, 3, 3]]) == report(
    7, 1, 2, 12, [0, 0, 3, 3]
), "two panels sharing one unit of ground"
assert panel_coverage([[0, 0, 4, 4], [1, 1, 2, 2]]) == report(
    16, 1, 2, 16, [0, 0, 4, 4]
), "a contained panel adds overlap but no union or boundary"
assert panel_coverage([[0, 0, 2, 1], [0, 0, 2, 1]]) == report(
    2, 2, 2, 6, [0, 0, 2, 1]
), "identical panels overlap over their whole area"
assert panel_coverage([[0, 0, 2, 2], [1, 0, 3, 2], [0, 1, 2, 3]]) == report(
    8, 3, 3, 12, [0, 0, 3, 3]
), "three panels stacking over a common core"
assert panel_coverage([[0, 0, 2, 1], [1, 0, 3, 1], [2, 0, 4, 1]]) == report(
    4, 2, 2, 10, [0, 0, 4, 1]
), "a chain overlaps pairwise but never stacks three deep"
assert panel_coverage([[-2, -2, 1, 1], [-1, -1, 2, 2]]) == report(
    14, 4, 2, 16, [-2, -2, 2, 2]
), "negative coordinates measure the same way"
assert panel_coverage([[0, -3, 1, 3], [-3, 0, 3, 1]]) == report(
    11, 1, 2, 24, [-3, -3, 3, 3]
), "a cross keeps every arm's boundary"
assert panel_coverage([[0, 0, 2, 2], [0, 0, 2, 2], [0, 0, 2, 2]]) == report(
    4, 4, 3, 8, [0, 0, 2, 2]
), "a triple stack reads three deep"


def rejects(panels):
    try:
        panel_coverage(panels)
    except Exception:
        return True
    return False


assert rejects("x"), "non-list panels is rejected"
assert rejects([[0, 0, 1]]), "a three-item panel is rejected"
assert rejects([[0, 0, 1.5, 1]]), "a fractional coordinate is rejected"
assert rejects([[0, "0", 1, 1]]), "a string coordinate is rejected"
assert rejects([[2, 0, 1, 1]]), "reversed x edges are rejected"
assert rejects([[1, 0, 1, 2]]), "a zero-width panel is rejected"
assert rejects([[0, 3, 2, 1]]), "reversed y edges are rejected"
print("ok")
