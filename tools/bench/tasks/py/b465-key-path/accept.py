from solution import key_path

assert key_path({"a.b": "1"}, "a") == ["b"], "one name under the head"
assert key_path({"a.b.c": "1"}, "a") == [], "a deeper name is left out"
assert key_path({"b": "1"}, "a") == [], "nothing is under the head"
assert key_path({}, "a") == [], "an empty store"
assert key_path({"a.b": "1", "a.c": "2"}, "a") == [
    "b",
    "c",
], "two names under one head"
assert key_path({"a.b": "1", "x.y": "2"}, "x") == ["y"], "a different head"
print("ok")
