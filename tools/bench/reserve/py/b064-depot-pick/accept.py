from solution import nearest_depot, taxi_distance

assert taxi_distance([0, 0], [3, 4]) == 7, "blocks east plus blocks south"
assert taxi_distance([2, -1], [-2, 3]) == 8, "both differences count as magnitudes"
assert nearest_depot([0, 0], [[5, 0], [1, 1], [0, 3]]) == 1, "closest of three depots"
assert nearest_depot([2, 2], [[2, 2]]) == 0, "a lone depot wins"
assert nearest_depot([0, 0], [[2, 0], [0, 2], [1, 1]]) == 0, "a distance tie goes to the lowest index"
assert nearest_depot([0, 0], [[1, 0], [-4, 0]]) == 0, "a depot west of the origin is not nearer than it is"
assert nearest_depot([0, 0], [[0, -6], [0, 2]]) == 1, "a depot north of the origin is not nearer than it is"
assert nearest_depot([3, 3], [[3, 3], [4, 4]]) == 0, "standing at a depot is distance zero"


def rejects(origin, depots):
    try:
        nearest_depot(origin, depots)
    except Exception:
        return True
    return False


assert rejects([0, 0], []), "empty depot list is rejected"
assert rejects([0, 0], [[1.5, 0]]), "fractional depot coordinate is rejected"
assert rejects([0.5, 0], [[1, 0]]), "fractional origin coordinate is rejected"
print("ok")
