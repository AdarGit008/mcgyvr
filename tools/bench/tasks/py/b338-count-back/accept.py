from solution import count_back

assert count_back(3) == [3, 2, 1], "down to one and no further"
assert count_back(1) == [1], "a start of one"
assert count_back(0) == [], "a start of zero counts nothing"
assert count_back(-2) == [], "a start below zero counts nothing"
assert count_back(5) == [5, 4, 3, 2, 1], "a longer count"
assert count_back(2) == [2, 1], "a short one"
print("ok")
