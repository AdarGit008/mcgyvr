from solution import run_patrol, clamp_move

assert run_patrol(5, 2, []) == {
    "position": 2,
    "bumps": 0,
    "visited": 1,
}, "no moves stays put"
assert run_patrol(4, 1, [9]) == {
    "position": 3,
    "bumps": 1,
    "visited": 2,
}, "a long move stops at the far wall"
assert run_patrol(3, 1, [-5, 6]) == {
    "position": 2,
    "bumps": 2,
    "visited": 3,
}, "both walls cut moves short"
assert run_patrol(5, 2, [1, -1]) == {
    "position": 2,
    "bumps": 0,
    "visited": 2,
}, "returning to a cell adds nothing"
assert clamp_move(2, 10, 5) == [4, True], "helper clamps at the far wall"


def rejects(*args):
    try:
        run_patrol(*args)
    except ValueError:
        return True
    return False


assert rejects(0, 0, [1]), "zero width is rejected"
assert rejects(4, 4, [1]), "start outside the corridor is rejected"
assert rejects(4, 2, [0]), "zero move is rejected"
assert rejects(4, 2, "east"), "non-list moves argument is rejected"
print("ok")
