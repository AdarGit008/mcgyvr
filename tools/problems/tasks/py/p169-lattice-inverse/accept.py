from solution import lattice_inverse

assert lattice_inverse([[1, 2], [0, 1]]) == [[1, -2], [0, 1]], "a shear undone"
assert lattice_inverse([[2, 3], [1, 2]]) == [[2, -3], [-1, 2]], "determinant one"
assert lattice_inverse([[0, -1], [1, 0]]) == [[0, 1], [-1, 0]], "a quarter turn"
assert lattice_inverse([[3, 4], [5, 7]]) == [[7, -4], [-5, 3]], "larger entries"
assert lattice_inverse([[1, 1], [2, 1]]) == [[-1, 1], [2, -1]], "determinant -1"
assert lattice_inverse([[1, 2], [3, 4]]) == [], "determinant -2 cannot be undone"
assert lattice_inverse([[2, 4], [1, 2]]) == [], "a flat frame cannot be undone"
assert lattice_inverse([[1, 2, 3], [0, 1, 4], [0, 0, 1]]) == [
    [1, -2, 5],
    [0, 1, -4],
    [0, 0, 1],
], "three rows, upper corner clear"
assert lattice_inverse([[0, 0, 1], [1, 0, 0], [0, 1, 0]]) == [
    [0, 1, 0],
    [0, 0, 1],
    [1, 0, 0],
], "a three-way shuffle"
assert lattice_inverse([[2, 3, 1], [1, 2, 1], [1, 1, 1]]) == [
    [1, -2, 1],
    [0, 1, -1],
    [-1, 1, 1],
], "three rows, dense"
assert lattice_inverse([[0, 1, 4], [1, 2, 3], [0, 0, 1]]) == [
    [-2, 1, 5],
    [1, 0, -4],
    [0, 0, 1],
], "three rows, determinant minus one"
assert lattice_inverse([[2, 0, 0], [0, 1, 0], [0, 0, 1]]) == [], "determinant two"
assert lattice_inverse([[1, 2, 3], [4, 5, 6], [7, 8, 9]]) == [], "three flat rows"


def rejects(frame):
    try:
        lattice_inverse(frame)
    except ValueError:
        return True
    return False


assert rejects([[1]]), "one row rejected"
assert rejects("f"), "non-list rejected"
assert rejects([[1, 2], [3]]), "ragged rows rejected"
assert rejects([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]), "four rows"
assert rejects([[1, 0.5], [0, 1]]), "fractional entry rejected"
print("ok")
