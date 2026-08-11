from solution import rename_field

assert rename_field([{"a": 1}], "a", "b") == [{"b": 1}], "the old name goes"
assert rename_field([{"c": 1}], "a", "b") == [{"c": 1}], "no such field"
assert rename_field([], "a", "b") == [], "no records at all"
assert rename_field([{"a": 1, "c": 2}], "a", "b") == [
    {"b": 1, "c": 2}
], "other fields are kept"
assert rename_field([{"a": 1}, {"a": 2}], "a", "b") == [
    {"b": 1},
    {"b": 2},
], "every record is renamed"

source = [{"a": 1}]
rename_field(source, "a", "b")
assert source == [{"a": 1}], "the records given are untouched"
print("ok")
