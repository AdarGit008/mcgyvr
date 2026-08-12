from solution import fold_rests

assert fold_rests(["a", "", "", "b"]) == ["a", "-", "b"], "a stretch of rests folds to one dash"
assert fold_rests(["a", " ", "b", "", "c"]) == ["a", "-", "b", "-", "c"], "two stretches stand apart"
assert fold_rests(["", "a"]) == ["-", "a"], "a run opening on a rest"
assert fold_rests(["a", "b"]) == ["a", "b"], "a run holding no rests"
assert fold_rests(["a", "  "]) == ["a", "-"], "blank space counts as a rest"
assert fold_rests([]) == [], "a run holding nothing"
print("ok")
