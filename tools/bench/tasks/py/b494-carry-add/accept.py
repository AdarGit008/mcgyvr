from solution import carry_add

assert carry_add([1, 2], [3, 4]) == [4, 6], "no place carries"
assert carry_add([5], [5]) == [1, 0], "a carry opens a new place"
assert carry_add([9, 9], [1]) == [1, 0, 0], "a carry runs the whole way"
assert carry_add([1, 0, 0], [2]) == [1, 0, 2], "runs of unlike length"
assert carry_add([0], [0]) == [0], "two figures of nothing"
assert carry_add([], []) == [], "two runs holding nothing"
print("ok")
