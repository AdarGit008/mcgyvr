from solution import fade_steps

assert fade_steps(8) == [8, 4, 2, 1], "a level that halves evenly"
assert fade_steps(5) == [5, 2, 1], "a part below a whole is dropped"
assert fade_steps(7) == [7, 3, 1], "an odd level all the way down"
assert fade_steps(20) == [20, 10, 5, 2, 1], "a longer run"
assert fade_steps(1) == [1], "a level of one"
assert fade_steps(0) == [], "nothing to begin with"
print("ok")
