from solution import mid_pair

assert mid_pair([1, 2, 3, 4]) == [2, 3], "the two middle values"
assert mid_pair([1, 2, 3]) == [2, 2], "an odd length gives one twice"
assert mid_pair([]) == [0, 0], "nothing at all"
assert mid_pair([5]) == [5, 5], "one value is its own middle"
assert mid_pair([4, 1, 3, 2]) == [2, 3], "the list is put in order first"
assert mid_pair([9, 1]) == [1, 9], "two values are both middle"
print("ok")
