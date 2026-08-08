from solution import triplet_chain_cells

assert triplet_chain_cells(
    [[0, 0, 2], [0, 1, 3], [1, 2, 4]],
    [[0, 1, 5], [1, 1, 7], [2, 0, 6]],
    2,
    3,
    2,
) == [
    [0, 1, 31],
    [1, 0, 24],
], "routes through several middles add, and the source orders ahead of the sink"

assert triplet_chain_cells(
    [[0, 0, 2], [0, 1, 3]],
    [[0, 0, 3], [1, 0, -2]],
    1,
    2,
    1,
) == [], "a pair whose routes cancel is dropped"

assert triplet_chain_cells([[0, 0, 5]], [], 1, 1, 1) == [
], "an empty second bag leaves no route at all"

assert triplet_chain_cells([], [[0, 0, 5]], 1, 1, 1) == [
], "an empty first bag leaves no route at all"

assert triplet_chain_cells([[0, 1, 6]], [[0, 0, 9]], 1, 2, 1) == [
], "a middle nothing leaves from yields no route, and the join is on the middle"

assert triplet_chain_cells(
    [[2, 0, 1], [0, 0, 1], [1, 0, 1]],
    [[0, 2, 1], [0, 0, 1]],
    3,
    1,
    3,
) == [
    [0, 0, 1],
    [0, 2, 1],
    [1, 0, 1],
    [1, 2, 1],
    [2, 0, 1],
    [2, 2, 1],
], "a full cross product comes back in source-then-sink order"

assert triplet_chain_cells([[0, 0, -10000]], [[0, 0, 10000]], 1, 1, 1) == [
    [0, 0, -100000000]
], "the weight limit multiplies out exactly"


def rejects(*args):
    try:
        triplet_chain_cells(*args)
    except ValueError:
        return True
    return False


assert rejects([[0, 3, 1]], [], 1, 3, 1), "a middle at the edge is rejected"
assert rejects([[0, 0, 1]], [[-1, 0, 1]], 1, 1, 1), "a negative endpoint is rejected"
assert rejects([[0, 0, 0]], [], 1, 1, 1), "a stored weight of nothing is rejected"
assert rejects([[0, 0, 1], [0, 0, 2]], [], 1, 1, 1), "a repeated link is rejected"
assert rejects([[0, 0, 10001]], [], 1, 1, 1), "an oversized weight is rejected"
assert rejects([[0, 0, 1]], [], 1, 0, 1), "a band width of nothing is rejected"
assert rejects([[0, 0]], [], 1, 1, 1), "a link that is not a triple is rejected"
assert rejects("bag", [], 1, 1, 1), "a bag that is not a list is rejected"
print("ok")
