from solution import char_run

assert char_run("aabbb") == 3, "the longer run wins"
assert char_run("abc") == 1, "no character repeats"
assert char_run("") == 0, "an empty text"
assert char_run("aaaa") == 4, "one run throughout"
assert char_run("a") == 1, "a single character"
assert char_run("aabaa") == 2, "two runs of the same length"
print("ok")
