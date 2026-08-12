from solution import till_float

assert till_float(30, [20, 10, 5]) == [1, 1, 0], "one of each of two coins"
assert till_float(45, [20, 10, 5]) == [2, 0, 1], "two of the largest coin"
assert till_float(7, [5, 1]) == [1, 2], "two of the smallest coin"
assert till_float(0, [10]) == [0], "nothing to hand back"
assert till_float(100, [50]) == [2], "the same coin twice over"
assert till_float(3, [5]) == [0], "the coin is too big"
print("ok")
