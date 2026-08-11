from solution import row_keys, merge_rows

assert row_keys({"a": "1", "b": "2"}) == ["a", "b"], "the names it holds"
assert row_keys({}) == [], "an empty row holds none"
assert merge_rows({"a": "1"}, {"a": "9"}) == {"a": "9"}, "the row above wins"
assert merge_rows({"a": "1"}, {"b": "2"}) == {
    "a": "1",
    "b": "2",
}, "no name is shared"
assert merge_rows({}, {}) == {}, "two empty rows"

source = {"a": "1"}
merge_rows(source, {"a": "9"})
assert source == {"a": "1"}, "the row below is untouched"
print("ok")
