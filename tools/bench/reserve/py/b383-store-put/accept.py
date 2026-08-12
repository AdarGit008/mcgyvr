from solution import put_one, put_all


def rejects(store, key, value):
    try:
        put_one(store, key, value)
    except Exception:
        return True
    return False


assert put_one({"a": "1"}, "b", "2") == {"a": "1", "b": "2"}, "a key is set"
assert put_one({"a": "1"}, "a", "9") == {"a": "9"}, "an existing key is replaced"
assert put_all({}, [["a", "1"], ["b", "2"]]) == {
    "a": "1",
    "b": "2",
}, "several keys at once"
assert put_all({"a": "1"}, []) == {"a": "1"}, "nothing to set"

source = {"a": "1"}
put_one(source, "b", "2")
assert source == {"a": "1"}, "the caller's store is untouched"
assert rejects({}, "", "x"), "an empty key is rejected"
print("ok")
