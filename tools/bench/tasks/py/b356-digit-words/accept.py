from solution import digit_word, digit_words

assert digit_word(0) == "zero", "the lowest digit"
assert digit_word(9) == "nine", "the highest digit"
assert digit_words("12") == "one two", "two digits named"
assert digit_words("7") == "seven", "a single digit"
assert digit_words("") == "", "no digits at all"
assert digit_words("305") == "three zero five", "a zero in the middle"
print("ok")
