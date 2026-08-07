from solution import splice_shifts

assert splice_shifts([[2, 10], [1]]) == [1, 2, 10], "numeric order, not text order"
assert splice_shifts([[1], [5], [3]]) == [1, 3, 5], "every sheet counts, not just two"
assert splice_shifts([[1, 2], [2, 3]]) == [1, 2, 3], "a badge on two sheets appears once"
assert splice_shifts([[4, 4, 4]]) == [4], "a badge repeated on one sheet appears once"
assert splice_shifts([[], [7], []]) == [7], "empty sheets contribute nothing"
assert splice_shifts([]) == [], "no sheets gives an empty roster"
assert splice_shifts([[1, 3, 5], [2, 3, 8], [0]]) == [
    0,
    1,
    2,
    3,
    5,
    8,
], "three sheets splice into one ordered roster"
assert splice_shifts([[], []]) == [], "only empty sheets gives an empty roster"
print("ok")
