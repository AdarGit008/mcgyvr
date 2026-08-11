from solution import slot_in

assert slot_in([1, 3, 5], 4) == [1, 3, 4, 5], "a reading landing in the middle"
assert slot_in([1, 3, 5], 0) == [0, 1, 3, 5], "a reading below everything"
assert slot_in([1, 3, 5], 9) == [1, 3, 5, 9], "a reading above everything"
assert slot_in([1, 3, 3, 5], 3) == [1, 3, 3, 3, 5], "a reading matching those there"
assert slot_in([2], 2) == [2, 2], "a run of one that matches"
assert slot_in([], 2) == [2], "a run holding nothing"
print("ok")
