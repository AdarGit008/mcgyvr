from solution import case_count

assert case_count("aB") == [1, 1], "one of each"
assert case_count("ABC") == [3, 0], "all capitals"
assert case_count("abc") == [0, 3], "all small"
assert case_count("") == [0, 0], "nothing at all"
assert case_count("12-!") == [0, 0], "no letters among them"
assert case_count("Hi There") == [2, 5], "a space counts as neither"
print("ok")
