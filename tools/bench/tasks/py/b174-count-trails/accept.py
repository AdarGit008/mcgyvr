from solution import count_trails

assert count_trails(1, 1, []) == 1, "a single cell is crossed one way"
assert count_trails(1, 5, []) == 1, "a single row leaves one route"
assert count_trails(2, 2, []) == 2, "a two by two floor has two routes"
assert count_trails(3, 3, []) == 6, "an open three by three floor has six routes"
assert count_trails(3, 3, [[1, 1]]) == 2, "a rope in the middle cuts the routes to two"
assert count_trails(2, 2, [[0, 1], [1, 0]]) == 0, "ropes across both middles leave no route"
assert count_trails(4, 3, [[1, 1]]) == 4, "one rope on a taller floor leaves four routes"


def rejects(rows, cols, blocked):
    try:
        count_trails(rows, cols, blocked)
    except Exception:
        return True
    return False


assert rejects(0, 3, []), "a floor with no rows is rejected"
assert rejects(2, 2, [[1]]), "a roped entry of one number is rejected"
assert rejects(2, 2, [[2, 0]]), "a roped cell off the floor is rejected"
assert rejects(2, 2, [[0, 0]]), "a rope across the entrance is rejected"
print("ok")
