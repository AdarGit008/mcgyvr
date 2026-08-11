from solution import strip_tags

assert strip_tags("a<b>c") == "ac", "the marker goes"
assert strip_tags("<p>hi</p>") == "hi", "markers at both ends"
assert strip_tags("plain") == "plain", "no markers at all"
assert strip_tags("") == "", "an empty line"
assert strip_tags("a<b") == "a", "an unclosed marker eats the rest"
assert strip_tags("<a><b>x") == "x", "two markers in a row"
print("ok")
