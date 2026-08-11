from solution import drop_blank

assert drop_blank(["a", "", "b"]) == ["a", "b"], "the empty one goes"
assert drop_blank(["a", " ", "b"]) == ["a", " ", "b"], "a space is not empty"
assert drop_blank([]) == [], "nothing to drop"
assert drop_blank(["", ""]) == [], "everything is empty"
assert drop_blank(["  "]) == ["  "], "spaces alone survive"
assert drop_blank(["x"]) == ["x"], "nothing needs dropping"
print("ok")
