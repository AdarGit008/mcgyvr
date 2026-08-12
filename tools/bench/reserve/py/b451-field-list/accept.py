from solution import field_or, field_list

assert field_or({"a": "1"}, "a", "-") == "1", "the field is held"
assert field_or({}, "a", "-") == "-", "the stand-in is used"
assert field_list([{"a": "1"}, {}], "a", "-") == ["1", "-"], "one of each"
assert field_list([], "a", "-") == [], "no records at all"
assert field_list([{"b": "1"}], "a", "-") == ["-"], "the field is never held"
assert field_or({"a": ""}, "a", "-") == "", "an empty value is still a value"
print("ok")
