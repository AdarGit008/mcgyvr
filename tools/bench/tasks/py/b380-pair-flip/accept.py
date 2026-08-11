from solution import flip_one, flip_all

assert flip_one(["a", "b"]) == ["b", "a"], "one pair turns round"
assert flip_one(["x", "x"]) == ["x", "x"], "a pair of the same"
assert flip_all([["a", "b"], ["c", "d"]]) == [
    ["b", "a"],
    ["d", "c"],
], "each pair"
assert flip_all([]) == [], "no pairs at all"
assert flip_all([["a", "b"]]) == [["b", "a"]], "a single pair"

source = [["a", "b"]]
flip_all(source)
assert source == [["a", "b"]], "the list it was given is untouched"
print("ok")
