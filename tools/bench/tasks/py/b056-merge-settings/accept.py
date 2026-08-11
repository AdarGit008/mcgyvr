from solution import merge_settings

assert merge_settings({"theme": "dark"}, {"theme": "dark"}, {"theme": "dark"}) == {
    "theme": "dark"
}, "identical sides come back unchanged"
assert merge_settings({"lang": "en"}, {"lang": "fr"}, {"lang": "en"}) == {
    "lang": "fr"
}, "our lone edit wins"
assert merge_settings({"tab": "4"}, {"tab": "2"}, {"tab": "2"}) == {
    "tab": "2"
}, "the same edit on both sides is kept once"
assert merge_settings(
    {"a": "1", "b": "2"}, {"a": "1", "b": "2", "c": "3"}, {"b": "2"}
) == {"b": "2", "c": "3"}, "an addition by us and a deletion by them merge cleanly"
assert merge_settings({}, {}, {}) == {}, "empty sides merge to empty"


def rejects(*args):
    try:
        merge_settings(*args)
    except ValueError:
        return True
    return False


assert rejects({"x": "1"}, {"x": "2"}, {"x": "3"}), "two different edits conflict"
assert rejects({"x": "1"}, {"x": "2"}, {}), "an edit against a deletion conflicts"
assert rejects([], {}, {}), "an array side is rejected"
assert rejects({}, {"n": 7}, {}), "a non-string value is rejected"
print("ok")
