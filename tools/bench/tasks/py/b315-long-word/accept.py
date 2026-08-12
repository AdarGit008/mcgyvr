from solution import long_word

assert long_word("a bb ccc") == "ccc", "the longest wins"
assert long_word("aa bb") == "aa", "a tie goes to the first"
assert long_word("") == "", "no sentence, no word"
assert long_word("   ") == "", "spaces hold no words"
assert long_word("one") == "one", "a single word"
assert long_word("to the point") == "point", "the last is longest"
print("ok")
