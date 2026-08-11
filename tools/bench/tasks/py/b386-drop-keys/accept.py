from solution import drop_keys

assert drop_keys({"a": 1, "b": 2}, ["a"]) == {"b": 2}, "the named key goes"
assert drop_keys({"a": 1}, ["b"]) == {"a": 1}, "an absent key changes nothing"
assert drop_keys({}, ["a"]) == {}, "an empty store"
assert drop_keys({"a": 1}, ["a"]) == {}, "everything is dropped"
assert drop_keys({"a": 1, "b": 2}, []) == {"a": 1, "b": 2}, "nothing is named"

source = {"a": 1, "b": 2}
drop_keys(source, ["a"])
assert source == {"a": 1, "b": 2}, "the store it was given is untouched"
print("ok")
