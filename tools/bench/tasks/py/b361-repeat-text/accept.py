from solution import repeat_text

assert repeat_text("ha", 3, "-") == "ha-ha-ha", "three copies joined"
assert repeat_text("ha", 1, "-") == "ha", "one copy takes no separator"
assert repeat_text("ha", 0, "-") == "", "no copies at all"
assert repeat_text("ha", -2, "-") == "", "fewer than none is still none"
assert repeat_text("", 3, "-") == "--", "an empty phrase still separates"
assert repeat_text("x", 2, ", ") == "x, x", "a longer separator"
print("ok")
