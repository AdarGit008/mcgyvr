from solution import top_keys

assert top_keys({"a": 1, "b": 3}) == ["b"], "one clear leader"
assert top_keys({"b": 2, "a": 2}) == ["a", "b"], "a tie in alphabetical order"
assert top_keys({}) == [], "an empty mapping"
assert top_keys({"x": 5}) == ["x"], "one name is the leader"
assert top_keys({"a": 0, "b": 0}) == ["a", "b"], "everything ties at nothing"
assert top_keys({"c": 1, "a": 4, "b": 4}) == ["a", "b"], "two share the top"
print("ok")
