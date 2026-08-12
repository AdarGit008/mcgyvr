from solution import every_other

assert every_other(["a", "b", "c"]) == ["a", "c"], "the first and the third"
assert every_other(["a", "b", "c", "d"]) == ["a", "c"], "an even-length log"
assert every_other(["a"]) == ["a"], "one entry comes back"
assert every_other([]) == [], "an empty log"
assert every_other(["a", "b"]) == ["a"], "only the first of a pair"
assert every_other(["p", "q", "r", "s", "t"]) == ["p", "r", "t"], "three from five"
print("ok")
