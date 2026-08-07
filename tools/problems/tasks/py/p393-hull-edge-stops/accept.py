from solution import hull_edge_stops

assert (
    hull_edge_stops([[0, 0], [1, 0], [1, 1], [0, 1]]) == 4
), "the unit square touches its four turning posts and nothing else"

assert (
    hull_edge_stops([[0, 0], [2, 0], [2, 2], [0, 2], [1, 1]]) == 8
), "a two-wide square touches eight, and the peg inside is ignored"

assert (
    hull_edge_stops([[0, 0], [4, 0], [0, 3]]) == 8
), "the 4 by 3 triangle: four along the base, three up the side, one on the slant"

assert (
    hull_edge_stops([[-3, -3], [3, -3], [3, 3], [-3, 3]]) == 24
), "a six-wide square around the origin"

assert (
    hull_edge_stops([[0, 0], [3, 0], [1, 0]]) == 4
), "a flat run is walked once, not twice"

assert (
    hull_edge_stops([[0, 0], [4, 6]]) == 3
), "a slanted run stops only where the run meets the grid"

assert (
    hull_edge_stops([[5, -2], [5, -2]]) == 1
), "one spot touches exactly one grid point"

assert hull_edge_stops([[0, 0]]) == 1, "a lone peg touches one"


def rejects(*args):
    try:
        hull_edge_stops(*args)
    except ValueError:
        return True
    return False


assert rejects([]), "an empty list is rejected"
assert rejects(17), "a non-list is rejected"
assert rejects([[1]]), "a single number is not a peg"
assert rejects([[0, 0], ["2", 2]]), "a text coordinate is rejected"
assert rejects([[0, 0], [1, 1000001]]), "an oversized coordinate is rejected"
print("ok")
