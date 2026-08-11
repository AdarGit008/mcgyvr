from solution import first_over

assert first_over([1, 7, 9], 3) == 7, "the reading, not its place"
assert first_over([9], 3) == 9, "the first reading is already over"
assert first_over([1, 2], 3) == 0, "nothing stands above"
assert first_over([], 3) == 0, "no readings at all"
assert first_over([3, 4], 3) == 4, "a reading on the level is not over it"
assert first_over([1, 1, 5], 3) == 5, "the third reading"
print("ok")
