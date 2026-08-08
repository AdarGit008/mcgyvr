from solution import repair_replicas

assert repair_replicas([[1, 2], [1, 2], [1, 3]]) == [
    1,
    2,
], "two of three agree at each position"
assert repair_replicas([[1, None], [1, 5], [2, 5]]) == [
    1,
    5,
], "a lost slot shrinks the denominator, so 2 of 2 survivors is a majority"
assert repair_replicas([[4, 9], [None, 9], [4, 9]]) == [
    4,
    9,
], "survivors can agree unanimously around a hole"
assert repair_replicas([[7, 8]]) == [7, 8], "one replica is its own majority"
assert repair_replicas([[], [], []]) == [], "empty replicas rebuild to empty"


def rejects(replicas):
    try:
        repair_replicas(replicas)
    except ValueError:
        return True
    return False


assert rejects([[1], [2]]), "a one-against-one split has no strict majority"
assert rejects([[1, None], [1, None]]), "a position lost everywhere is unrecoverable"
assert rejects([]), "an empty replica list is rejected"
assert rejects([[1, 2], [1]]), "ragged replica lengths are rejected"
assert rejects([["x"], ["x"]]), "a non-integer slot is rejected"
assert rejects(
    [[1, 1], [2, 1], [2, 1], [3, 1]]
), "a mere plurality of 2 in 4 is not a strict majority"
print("ok")
