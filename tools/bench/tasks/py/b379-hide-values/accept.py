from solution import hide_values

assert hide_values({"a": "xy"}) == {"a": "**"}, "one star per character"
assert hide_values({}) == {}, "nothing to hide"
assert hide_values({"ab": ""}) == {"ab": ""}, "an empty value hides to nothing"
assert hide_values({"a": "x", "b": "yz"}) == {
    "a": "*",
    "b": "**",
}, "each value keeps its own length"
assert hide_values({"k": "abc"}) == {"k": "***"}, "a longer value"
assert hide_values({"longkey": "x"}) == {"longkey": "*"}, "the key is untouched"
print("ok")
