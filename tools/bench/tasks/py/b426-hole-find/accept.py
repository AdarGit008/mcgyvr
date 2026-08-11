from solution import steps_on, hole_find

assert steps_on(1, 3) == [1, 2, 3], "three numbers from one"
assert steps_on(5, 0) == [], "no numbers at all"
assert hole_find([1, 3], 1, 3) == 2, "the missing number"
assert hole_find([1, 2, 3], 1, 3) == 0, "nothing is missing"
assert hole_find([], 1, 2) == 1, "everything is missing"
assert hole_find([2, 3], 1, 3) == 1, "the first is missing"
print("ok")
