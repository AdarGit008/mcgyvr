from solution import day_next

assert day_next(0, 1) == 1, "tomorrow"
assert day_next(1, 0) == 6, "round the week"
assert day_next(3, 3) == 7, "today is a whole week away"
assert day_next(6, 0) == 1, "over the end of the week"
assert day_next(0, 6) == 6, "the far end of the week"
assert day_next(2, 5) == 3, "three days on"
print("ok")
