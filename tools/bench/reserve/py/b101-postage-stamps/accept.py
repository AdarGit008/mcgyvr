from solution import fewest_stamps

assert fewest_stamps(6, [1, 3, 4]) == {
    "count": 2,
    "stamps": [3, 3],
}, "greedy would take 4+1+1; two threes win"
assert fewest_stamps(0, [5]) == {
    "count": 0,
    "stamps": [],
}, "zero postage needs no stamps"
assert fewest_stamps(12, [4]) == {
    "count": 3,
    "stamps": [4, 4, 4],
}, "a single denomination repeats"
assert fewest_stamps(7, [3, 4]) == {
    "count": 2,
    "stamps": [4, 3],
}, "stamps come back in non-increasing order"
assert fewest_stamps(10, [2, 5]) == {
    "count": 2,
    "stamps": [5, 5],
}, "two fives beat five twos"
assert fewest_stamps(6, [1, 2, 3, 4, 5]) == {
    "count": 2,
    "stamps": [5, 1],
}, "ties prefer the largest stamp at each step"
assert fewest_stamps(6, [4, 3, 1]) == {
    "count": 2,
    "stamps": [3, 3],
}, "denomination order does not matter"
assert fewest_stamps(2, [2]) == {
    "count": 1,
    "stamps": [2],
}, "one stamp can be the whole answer"


def rejects(postage, denominations):
    try:
        fewest_stamps(postage, denominations)
    except Exception:
        return True
    return False


assert rejects(7, [2, 4]), "odd postage from even stamps"
assert rejects(3, [5]), "postage below the smallest stamp"
assert rejects(2.5, [1]), "fractional postage is rejected"
assert rejects(5, []), "an empty denomination list"
assert rejects(5, [0, 5]), "a zero denomination is rejected"
assert rejects(5, [2, 2]), "a repeated denomination"
print("ok")
