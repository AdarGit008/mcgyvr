from solution import locker_gap

assert locker_gap([1, 2, 4]) == 3, "the hole in the middle"
assert locker_gap([3, 1, 2]) == 4, "order does not matter"
assert locker_gap([2, 2, 3]) == 1, "the first is free"
assert locker_gap([]) == 1, "nothing in use"
assert locker_gap([1, 1, 1]) == 2, "repeats count once"
assert locker_gap([5]) == 1, "a lone high locker"
assert locker_gap([1, 2, 3]) == 4, "past the highest"
print("ok")
