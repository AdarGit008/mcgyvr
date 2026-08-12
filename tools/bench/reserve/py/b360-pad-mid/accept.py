from solution import pad_side, pad_mid

assert pad_side(3) == "   ", "three spaces"
assert pad_side(0) == "", "no spaces at all"
assert pad_mid("ab", 6) == "  ab  ", "shared evenly"
assert pad_mid("ab", 5) == " ab  ", "the extra space goes right"
assert pad_mid("abc", 3) == "abc", "the word fills the field"
assert pad_mid("abcd", 2) == "abcd", "a wide word is left alone"
print("ok")
