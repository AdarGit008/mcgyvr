from solution import first_repeat

assert first_repeat(["a", "b", "a", "c"]) == "a", "the first entry arrives twice"
assert first_repeat(["a", "b", "c", "b"]) == "b", "the second arrival decides, not the first"
assert first_repeat(["x", "x"]) == "x", "a run of two that match"
assert first_repeat(["a", "b", "c"]) == "", "every entry arrives once"
assert first_repeat(["a"]) == "", "a lone entry"
assert first_repeat([]) == "", "a run holding nothing"
print("ok")
