from solution import value_keys

assert value_keys({"a": "x", "b": "x"}) == {"x": 2}, "two keys share a value"
assert value_keys({"a": "x"}) == {"x": 1}, "one key, one value"
assert value_keys({}) == {}, "an empty store"
assert value_keys({"a": "x", "b": "y"}) == {"x": 1, "y": 1}, "two separate values"
assert value_keys({"a": ""}) == {"": 1}, "an empty value counts"
assert value_keys({"a": "x", "b": "x", "c": "y"}) == {
    "x": 2,
    "y": 1,
}, "a mix of shared and lone"
print("ok")
