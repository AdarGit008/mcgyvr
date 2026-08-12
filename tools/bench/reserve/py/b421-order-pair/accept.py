from solution import low_of, order_pairs

assert low_of([3, 1]) == 1, "the smaller of the two"
assert low_of([2, 2]) == 2, "a pair of the same"
assert order_pairs([[5, 9], [1, 100]]) == [
    [1, 100],
    [5, 9],
], "ordered by the smaller number"
assert order_pairs([]) == [], "no pairs at all"
assert order_pairs([[1, 2]]) == [[1, 2]], "a single pair"
assert order_pairs([[1, 9], [1, 3]]) == [
    [1, 9],
    [1, 3],
], "a tie leaves the earlier pair earlier"
print("ok")
