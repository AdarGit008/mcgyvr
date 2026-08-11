from solution import wrap_words

assert wrap_words("a bb ccc", 5) == ["a bb", "ccc"], "a line fills then breaks"
assert wrap_words("one two three", 3) == [
    "one",
    "two",
    "three",
], "a word wider than the width stands alone"
assert wrap_words("verylongword", 4) == ["verylongword"], "one long word"
assert wrap_words("", 5) == [], "no sentence, no lines"
assert wrap_words("a b c d", 3) == ["a b", "c d"], "two to a line"
assert wrap_words("  spaced   out  ", 20) == ["spaced out"], "gaps collapse"
print("ok")
