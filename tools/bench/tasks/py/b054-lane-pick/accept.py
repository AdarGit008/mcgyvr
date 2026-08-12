from solution import pick_lane

assert pick_lane([4, 2, 7], []) == 1, "the shortest queue wins"
assert pick_lane([3, 1, 1], []) == 1, "a tie goes to the lowest index"
assert pick_lane([0, 5, 2], [0]) == 2, "a closed first lane is never picked"
assert pick_lane([4, 1, 3], [1]) == 2, "a closed shortest lane is skipped"
assert pick_lane([2], []) == 0, "a single open lane is picked"


def rejects(queues, closed):
    try:
        pick_lane(queues, closed)
    except Exception:
        return True
    return False


assert rejects([], []), "empty queues are rejected"
assert rejects([1, 2], [0, 1]), "all lanes closed is rejected"
assert rejects([1, -2], []), "a negative length is rejected"
assert rejects([1, 2], [5]), "an out-of-range closed index is rejected"
print("ok")
