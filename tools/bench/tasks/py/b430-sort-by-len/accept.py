from solution import sort_by_len

assert sort_by_len(["ccc", "a", "bb"]) == ["a", "bb", "ccc"], "shortest first"
assert sort_by_len(["bb", "aa"]) == ["aa", "bb"], "a tie goes alphabetically"
assert sort_by_len([]) == [], "no words at all"
assert sort_by_len(["one"]) == ["one"], "a single word"
assert sort_by_len(["b", "a", "cc"]) == ["a", "b", "cc"], "ties then length"

source = ["bb", "a"]
sort_by_len(source)
assert source == ["bb", "a"], "the list it was given is untouched"
print("ok")
