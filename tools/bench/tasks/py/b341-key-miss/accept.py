from solution import look_up

assert look_up({"a": "1"}, "a", "x") == "1", "the stored value"
assert look_up({}, "a", "x") == "x", "an absent key takes the fallback"
assert look_up({"a": ""}, "a", "x") == "", "an empty value is still a value"
assert look_up({"a": "1"}, "b", "x") == "x", "a different key is absent"
assert look_up({"a": "0"}, "a", "x") == "0", "a zero is a value too"
assert look_up({"b": "y"}, "b", "") == "y", "the fallback may be empty"
print("ok")
