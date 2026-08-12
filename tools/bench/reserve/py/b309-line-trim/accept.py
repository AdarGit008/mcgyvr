from solution import line_trim

assert line_trim("a  \nb") == "a\nb", "the tail goes"
assert line_trim("  a") == "  a", "a leading space stays"
assert line_trim("a\n  \nb") == "a\n\nb", "a line of spaces empties"
assert line_trim("") == "", "nothing to trim"
assert line_trim("no trailing") == "no trailing", "already clean"
assert line_trim("x   ") == "x", "the last line counts too"
print("ok")
