from solution import take_back

assert take_back([1, 2, 3], 3) == 1, "the last entry alone reaches it"
assert take_back([1, 2, 3], 5) == 2, "two from the end"
assert take_back([1, 2, 3], 99) == -1, "the whole list never reaches it"
assert take_back([], 1) == -1, "an empty list"
assert take_back([5], 5) == 1, "one entry exactly reaches it"
assert take_back([1, 1, 1], 2) == 2, "two of three"
print("ok")
