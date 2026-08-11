from solution import split_agenda

assert split_agenda([], 30) == [], "an empty agenda has no blocks"
assert split_agenda([[0, 20]], 30) == [[0, 20]], "a short session stays whole"
assert split_agenda([[0, 30]], 30) == [[0, 30]], "an exact fit stays whole"
assert split_agenda([[0, 40]], 20) == [[0, 20], [20, 40]], "an even cut lands on the midpoint"
assert split_agenda([[0, 45]], 25) == [[0, 23], [23, 45]], "the front half takes the extra minute"
assert split_agenda([[0, 10]], 3) == [
    [0, 3],
    [3, 5],
    [5, 8],
    [8, 10],
], "halving repeats until every block fits"
assert split_agenda([[-4, 4]], 4) == [[-4, 0], [0, 4]], "negative minutes halve cleanly"
assert split_agenda([[0, 10], [10, 15]], 5) == [
    [0, 5],
    [5, 10],
    [10, 15],
], "touching sessions keep their own blocks"
assert split_agenda([[0, 6], [9, 11]], 10) == [
    [0, 6],
    [9, 11],
], "a gap between sessions is preserved"


def rejects(sessions, limit):
    try:
        split_agenda(sessions, limit)
    except ValueError:
        return True
    return False


assert rejects([[0, 10]], 0), "a zero limit is rejected"
assert rejects([[0, 10]], 2.5), "a fractional limit is rejected"
assert rejects([[5, 5]], 10), "an empty session is rejected"
assert rejects([[0, 10], [5, 12]], 20), "overlapping sessions are rejected"
assert rejects([[0, 2.5]], 10), "a fractional bound is rejected"
print("ok")
