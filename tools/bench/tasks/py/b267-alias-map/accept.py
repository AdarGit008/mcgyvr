from solution import alias_resolve, alias_names

assert alias_resolve({"a": "b"}, "a") == "b", "one hop"
assert alias_resolve({"a": "b", "b": "c"}, "a") == "b", "no second hop is taken"
assert alias_resolve({"a": "b"}, "z") == "z", "a name that stands for nothing"
assert alias_resolve({}, "x") == "x", "no aliases at all"
assert alias_names({"birch": "b", "alder": "a"}) == ["alder", "birch"], "sorted"
assert alias_names({}) == [], "no names to list"
print("ok")
