from solution import up_runs

assert up_runs([1, 2, 3]) == 3, "the whole list rises"
assert up_runs([3, 2, 1]) == 1, "nothing rises"
assert up_runs([1, 5, 2, 3, 4]) == 3, "the later run is longer"
assert up_runs([]) == 0, "no readings at all"
assert up_runs([7]) == 1, "one reading is a run of one"
assert up_runs([1, 1, 2]) == 2, "a flat step breaks the run"
print("ok")
