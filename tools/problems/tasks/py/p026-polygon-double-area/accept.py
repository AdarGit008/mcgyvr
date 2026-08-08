from solution import polygon_double_area

assert polygon_double_area([[0, 0], [1, 0], [1, 1], [0, 1]]) == 2, "unit square"
assert polygon_double_area([[0, 0], [4, 0], [0, 3]]) == 12, "right triangle"
assert polygon_double_area([[0, 0], [0, 1], [1, 1], [1, 0]]) == 2, "clockwise matches"
assert polygon_double_area([[0, 0], [4, 0], [4, 4], [2, 2], [0, 4]]) == 24, "concave notch"
assert polygon_double_area(
    [[10, 10], [11, 10], [11, 11], [10, 11]]
) == 2, "translation does not change area"
assert polygon_double_area([[-1, -1], [1, -1], [1, 1], [-1, 1]]) == 8, "negative coords"
assert polygon_double_area([[0, 0], [2, 0], [4, 1]]) == 2, "thin sliver triangle"
assert polygon_double_area([[0, 0], [2, 0], [4, 0]]) == 0, "collinear encloses nothing"


def rejects(value):
    try:
        polygon_double_area(value)
    except ValueError:
        return True
    return False


assert rejects([[0, 0], [1, 1]]), "two vertices rejected"
assert rejects([[0, 0], [0, 0], [1, 1]]), "repeated consecutive vertex rejected"
assert rejects([[0, 0], [1, 0], [1, 1], [0, 0]]), "closed ring input rejected"
assert rejects([[0, 0], [1.5, 0], [1, 1]]), "fractional coordinate rejected"
assert rejects([[0, 0], [1], [1, 1]]), "short pair rejected"
print("ok")
