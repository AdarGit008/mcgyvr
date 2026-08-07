from solution import lattice_route_count

assert lattice_route_count([[0, 0], [0, 0]]) == 2, "open 2x2 has two routes"
assert (
    lattice_route_count([[0, 0, 0], [0, 0, 0], [0, 0, 0]]) == 6
), "open 3x3 has six routes"
assert (
    lattice_route_count([[0, 1, 0], [0, 0, 0]]) == 1
), "cells past a first-row obstacle are not entry points"
assert lattice_route_count([[0, 1, 0]]) == 0, "a blocked single row cannot be crossed"
assert (
    lattice_route_count([[0], [1], [0]]) == 0
), "a blocked single column cannot be descended"
assert (
    lattice_route_count([[0, 0, 0], [0, 1, 0], [0, 0, 0]]) == 2
), "a centre obstacle leaves the two rim routes"
assert lattice_route_count([[0]]) == 1, "a single clear cell counts one route"
assert (
    lattice_route_count([[0, 0, 0, 0], [0, 1, 1, 0], [0, 0, 0, 0]]) == 2
), "a wall in the middle row"
assert lattice_route_count([[1, 0], [0, 0]]) == 0, "a marked start counts nothing"


def rejects(grid):
    try:
        lattice_route_count(grid)
    except ValueError:
        return True
    return False


assert rejects([[0, 0], [0]]), "ragged grid rejected"
assert rejects([[0, 5]]), "bad cell rejected"
assert rejects([]), "empty grid rejected"
print("ok")
