from solution import join_books


def rejects(first, second):
    try:
        join_books(first, second)
    except Exception:
        return True
    return False


assert join_books({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}, "names standing apart"
assert join_books({"a": 1}, {"a": 1}) == {"a": 1}, "a name agreeing in both"
assert join_books({}, {"b": 2}) == {"b": 2}, "a first book holding nothing"
assert join_books({"a": 1}, {}) == {"a": 1}, "a second book holding nothing"
assert join_books({}, {}) == {}, "two books holding nothing"
assert rejects({"a": 1}, {"a": 2}), "a name disagreeing is rejected"
print("ok")
