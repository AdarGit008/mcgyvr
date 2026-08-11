from solution import hug_text

assert hug_text("abc", "*") == "*abc*", "a bare text takes a mark at each end"
assert hug_text("*abc*", "*") == "*abc*", "a text already marked at both ends"
assert hug_text("*abc", "*") == "**abc*", "marked at the opening only"
assert hug_text("abc*", "*") == "*abc**", "marked at the closing only"
assert hug_text("**", "*") == "**", "a text that is two marks"
assert hug_text("", "*") == "**", "a text holding nothing"
print("ok")
