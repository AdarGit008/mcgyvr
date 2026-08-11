from solution import cap_after

assert cap_after("hi. there") == "Hi. There", "both sentences are capitalised"
assert cap_after("hi") == "Hi", "one sentence with no full stop"
assert cap_after("") == "", "an empty passage"
assert cap_after("a. b. c") == "A. B. C", "three short sentences"
assert cap_after("  hi") == "  Hi", "leading spaces are not letters"
assert cap_after("HI. ho") == "HI. Ho", "other letters are left alone"
print("ok")
