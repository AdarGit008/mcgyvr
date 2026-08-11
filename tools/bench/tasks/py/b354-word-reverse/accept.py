from solution import word_reverse

assert word_reverse("abc def") == "cba fed", "each word turns"
assert word_reverse("a") == "a", "one letter is its own reverse"
assert word_reverse("") == "", "an empty line"
assert word_reverse("  two  words  ") == "owt sdrow", "the gaps collapse"
assert word_reverse("ab") == "ba", "a two-letter word"
assert word_reverse("one two three") == "eno owt eerht", "order is kept"
print("ok")
