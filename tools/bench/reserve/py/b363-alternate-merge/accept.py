from solution import alternate_merge

assert alternate_merge(["a", "b"], ["1", "2"]) == ["a", "1", "b", "2"], "in turn"
assert alternate_merge(["a"], ["1", "2"]) == ["a", "1", "2"], "the right runs on"
assert alternate_merge(["a", "b"], ["1"]) == ["a", "1", "b"], "the left runs on"
assert alternate_merge([], []) == [], "two empty lists"
assert alternate_merge([], ["1"]) == ["1"], "only the right holds anything"
assert alternate_merge(["a"], []) == ["a"], "only the left holds anything"
print("ok")
