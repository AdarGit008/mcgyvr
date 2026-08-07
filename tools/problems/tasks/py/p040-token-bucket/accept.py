from solution import token_bucket

assert token_bucket(10, 2, [[0, 4], [1, 8], [2, 3], [5, 7], [5, 1]]) == [
    "grant",
    "grant",
    "refuse",
    "grant",
    "grant",
], "accrual, a refusal, and a same-instant follow-up"
assert token_bucket(5, 1, [[0, 3], [0, 3], [10, 5]]) == [
    "grant",
    "refuse",
    "grant",
], "no accrual within one instant and the top-up is capped"
assert token_bucket(3, 5, [[0, 4], [1, 3]]) == [
    "refuse",
    "grant",
], "a cost above capacity is refused even when full"
assert token_bucket(2, 0, [[0, 1], [100, 2], [100, 1], [101, 1]]) == [
    "grant",
    "refuse",
    "grant",
    "refuse",
], "a zero refill rate never restores anything"
assert token_bucket(4, 3, [[2, 4], [3, 4], [4, 4]]) == [
    "grant",
    "refuse",
    "grant",
], "a refusal leaves the balance untouched for the next accrual"
assert token_bucket(5, 2, []) == [], "an empty log has no labels"


def rejects(*args):
    try:
        token_bucket(*args)
    except ValueError:
        return True
    return False


assert rejects(0, 1, []), "zero capacity is rejected"
assert rejects(5, -1, []), "negative refill is rejected"
assert rejects(5, 1, [[0, 0]]), "zero cost is rejected"
assert rejects(5, 1, [[-1, 1]]), "negative arrival time is rejected"
assert rejects(5, 1, [[5, 1], [4, 1]]), "a backwards arrival is rejected"
print("ok")
