from solution import run_of, group_runs

assert run_of(["a", "a", "b"], 0) == 2, "two in a row"
assert run_of(["a"], 0) == 1, "a run of one"
assert group_runs(["a", "a", "b"]) == [["a", "a"], ["b"]], "the final run is kept"
assert group_runs([]) == [], "nothing breaks into nothing"
assert group_runs(["a"]) == [["a"]], "one entry is one run"
assert group_runs(["a", "b", "b"]) == [["a"], ["b", "b"]], "two runs"
print("ok")
