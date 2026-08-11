from solution import steer_forklift

assert steer_forklift(3, 2, []) == [0, 0], "no moves stays parked"
assert steer_forklift(3, 2, ["east", "east", "south"]) == [2, 1], "east then south"
assert steer_forklift(2, 2, ["east", "west", "east", "west"]) == [0, 0], "backtracking returns to the corner"
assert steer_forklift(3, 3, ["east", "east", "south", "south"]) == [2, 2], "the far corner is reachable"
assert steer_forklift(1, 5, ["south", "south", "south", "south"]) == [0, 4], "a single aisle allows only southward travel"


def rejects(aisles, bays, moves):
    try:
        steer_forklift(aisles, bays, moves)
    except Exception:
        return True
    return False


assert rejects(3, 2, ["west"]), "west off the start corner is rejected"
assert rejects(3, 2, ["north"]), "north off the start corner is rejected"
assert rejects(2, 2, ["east", "east"]), "a move past the east edge is rejected"
assert rejects(3, 2, ["up"]), "an unknown move word is rejected"
assert rejects(0, 2, []), "zero aisles is rejected"
assert rejects(3, 2.5, []), "a fractional bay count is rejected"
print("ok")
