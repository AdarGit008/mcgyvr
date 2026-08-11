from solution import fold_undo

assert fold_undo([], 4) == [], "no changes leave the stack empty"
assert fold_undo([["title", "a", "b"], ["body", "x", "y"]], 4) == [["title", "a", "b"], ["body", "x", "y"]], "changes to different fields stack up"
assert fold_undo([["title", "a", "b"], ["title", "b", "c"]], 4) == [["title", "a", "c"]], "two changes to one field merge into one entry"
assert fold_undo([["title", "a", "b"], ["title", "b", "a"]], 4) == [], "a merge back to the old value records nothing"
assert fold_undo([["body", "x", "y"], ["title", "a", "b"], ["title", "b", "a"], ["body", "y", "z"]], 4) == [["body", "x", "z"]], "a change merges with the entry a removal uncovered"
assert fold_undo([["one", "1", "2"], ["two", "1", "2"], ["six", "1", "2"]], 2) == [["two", "1", "2"], ["six", "1", "2"]], "the bottom entry falls off a full stack"
print("ok")
