from solution import has_all

assert has_all({"a": 1, "b": 2}, ["a"]) is True, "the key is held"
assert has_all({"a": 1}, ["a", "b"]) is False, "one key is missing"
assert has_all({}, []) is True, "nothing is needed"
assert has_all({}, ["a"]) is False, "an empty store holds nothing"
assert has_all({"a": 1}, []) is True, "a full store, nothing needed"
assert has_all({"a": 1, "b": 2}, ["a", "b"]) is True, "both keys are held"
print("ok")
