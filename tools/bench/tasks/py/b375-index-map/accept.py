from solution import index_map

assert index_map(["a", "b", "a"]) == {"a": [0, 2], "b": [1]}, "two places"
assert index_map(["x"]) == {"x": [0]}, "one label, one place"
assert index_map([]) == {}, "no labels at all"
assert index_map(["a", "a", "a"]) == {"a": [0, 1, 2]}, "the same label thrice"
assert index_map(["b", "a"]) == {"b": [0], "a": [1]}, "each holds one place"
assert index_map(["a", "b", "b"]) == {"a": [0], "b": [1, 2]}, "a later pair"
print("ok")
