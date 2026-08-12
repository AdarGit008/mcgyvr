from solution import word_tally

assert word_tally("a b a") == {"a": 2, "b": 1}, "one word twice"
assert word_tally("A a") == {"a": 2}, "case is ignored"
assert word_tally("") == {}, "no sentence, no tally"
assert word_tally("  x   y  ") == {"x": 1, "y": 1}, "wide gaps are one break"
assert word_tally("one") == {"one": 1}, "a single word"
assert word_tally("go go go") == {"go": 3}, "three of a kind"
print("ok")
