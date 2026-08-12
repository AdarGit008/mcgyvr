from solution import nest_get

assert nest_get({"a": {"b": "deep"}}, ["a", "b"]) == "deep", "two steps down"
assert nest_get({"a": "top"}, ["a"]) == "top", "one step down"
assert nest_get({"a": "top"}, ["b"]) == "", "the path leads nowhere"
assert nest_get({"a": "top"}, []) == "", "an empty path finds nothing"
assert nest_get({"a": {"b": "deep"}}, ["a"]) == "", "a mapping is not text"
assert nest_get({"a": {"b": {"c": "far"}}}, ["a", "b", "c"]) == "far", "three steps down"
print("ok")
