from solution import strip_ends

assert strip_ends("--a--", "-") == "a", "several from each end"
assert strip_ends("-a-", "-") == "a", "one from each end"
assert strip_ends("a", "-") == "a", "nothing to strip"
assert strip_ends("---", "-") == "", "everything is stripped"
assert strip_ends("", "-") == "", "an empty text"
assert strip_ends("--a", "-") == "a", "only the front carries them"
print("ok")
