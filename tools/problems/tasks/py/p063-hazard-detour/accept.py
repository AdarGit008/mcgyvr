from solution import hazard_detour

OPEN = [[0] * 5 for _ in range(5)]
assert hazard_detour(OPEN, [0, 0], [4, 4]) == 8, "open grid walks straight"
CENTRE = [
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0],
    [0, 0, 1, 0, 0],
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0],
]
assert (
    hazard_detour(CENTRE, [2, 0], [2, 4]) == 8
), "detours around the hazard and its four neighbours"
assert (
    hazard_detour([[0, 0, 0, 0], [0, 1, 0, 0]], [0, 0], [0, 3]) == -1
), "a hazard below the corridor closes it"
assert (
    hazard_detour([[0, 1], [0, 0]], [0, 0], [1, 0]) == -1
), "a start beside a hazard is unsafe"
assert hazard_detour([[0, 0], [0, 0]], [1, 1], [1, 1]) == 0, "start equals goal"
assert (
    hazard_detour([[0, 1], [0, 0]], [0, 0], [0, 0]) == -1
), "an unsafe cell is -1 even as both start and goal"
assert hazard_detour([[0, 0, 0]], [0, 0], [0, 2]) == 2, "strip with no hazards"


def rejects(*args):
    try:
        hazard_detour(*args)
    except ValueError:
        return True
    return False


assert rejects([], [0, 0], [0, 0]), "empty grid rejected"
assert rejects([[0, 0], [0]], [0, 0], [0, 1]), "ragged grid rejected"
assert rejects([[0, 2]], [0, 0], [0, 1]), "bad cell rejected"
assert rejects([[0, 0]], [5, 0], [0, 1]), "out-of-bounds start rejected"
assert rejects([[0, 0]], [0, 0], [0, -1]), "out-of-bounds goal rejected"
print("ok")
