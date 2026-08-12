from solution import run_total

assert run_total([5, 6, 1, 7], 3) == [11, 7], "two runs, the low one excluded"
assert run_total([5, 6], 3) == [11], "one unbroken run"
assert run_total([1, 2], 3) == [], "the floor is never reached"
assert run_total([], 3) == [], "no readings at all"
assert run_total([3], 3) == [3], "a run of one on the floor"
assert run_total([1, 5, 1], 3) == [5], "a run between two low readings"
print("ok")
