from solution import round_robin_finish

assert round_robin_finish([["a", 5], ["b", 2], ["c", 3]], 2) == [
    ["b", 4],
    ["c", 9],
    ["a", 10],
], "partial final slices must not inflate the clock"
assert round_robin_finish([["x", 1]], 4) == [
    ["x", 1]
], "a job shorter than the quantum finishes at its own burst"
assert round_robin_finish([["a", 3], ["b", 3]], 3) == [
    ["a", 3],
    ["b", 6],
], "exact multiples finish on quantum boundaries"
assert round_robin_finish([["a", 4], ["b", 1]], 1) == [
    ["b", 2],
    ["a", 5],
], "unit quantum interleaves the queue"
assert round_robin_finish([["a", 7]], 3) == [
    ["a", 7]
], "a lone job accumulates only its own work"
assert round_robin_finish([["p", 1], ["q", 5], ["r", 1]], 2) == [
    ["p", 1],
    ["r", 4],
    ["q", 7],
], "completion order follows the rotation"


def rejects(*args):
    try:
        round_robin_finish(*args)
    except ValueError:
        return True
    return False


assert rejects([["a", 1]], 0), "zero quantum is rejected"
assert rejects([["a", 0]], 2), "zero burst is rejected"
assert rejects([["a", 1], ["a", 2]], 2), "a duplicate job name is rejected"
assert rejects([[7, 1]], 2), "a non-string name is rejected"
print("ok")
