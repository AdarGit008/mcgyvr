from solution import turn_cost_route

assert turn_cost_route([[0]], 1, 1) == 0, "single cell costs nothing"
assert turn_cost_route([[0, 0, 0]], 2, 5) == 4, "straight strip has no turns"
assert (
    turn_cost_route([[0, 0, 0], [0, 0, 0], [0, 0, 0]], 1, 10) == 14
), "open 3x3 pays for exactly one turn"
assert (
    turn_cost_route(
        [[0, 0, 0, 0, 0], [0, 1, 0, 1, 0], [0, 1, 0, 1, 0], [0, 0, 0, 0, 0]], 1, 10
    )
    == 17
), "prefers the single-turn route among equally short ones"
MAZE = [
    [0, 1, 0, 0, 0, 0, 0],
    [0, 0, 0, 1, 0, 1, 0],
    [0, 1, 0, 0, 1, 0, 0],
    [0, 0, 1, 0, 0, 0, 0],
    [1, 0, 0, 0, 0, 1, 0],
]
assert turn_cost_route(MAZE, 1, 7) == 40, "a longer route with fewer turns wins"
assert turn_cost_route(MAZE, 1, 0) == 10, "free turns reduce to fewest moves"
assert turn_cost_route([[0, 1], [1, 0]], 1, 1) == -1, "walled off is -1"
assert turn_cost_route([[1, 0], [0, 0]], 1, 1) == -1, "walled start is -1"


def rejects(*args):
    try:
        turn_cost_route(*args)
    except ValueError:
        return True
    return False


assert rejects([[0, 0], [0]], 1, 1), "ragged grid rejected"
assert rejects([[0, 2], [0, 0]], 1, 1), "bad cell rejected"
assert rejects([], 1, 1), "empty grid rejected"
assert rejects([[0, 0]], 0, 1), "zero step cost rejected"
assert rejects([[0, 0]], 1, -1), "negative turn cost rejected"
assert rejects([[0, 0]], 1.5, 1), "fractional step cost rejected"
print("ok")
