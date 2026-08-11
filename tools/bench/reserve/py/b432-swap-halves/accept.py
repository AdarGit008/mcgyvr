from solution import swap_halves

assert swap_halves("abcd") == "cdab", "an even text turns about"
assert swap_halves("abc") == "cab", "the middle stays with the first half"
assert swap_halves("a") == "a", "one character cannot move"
assert swap_halves("") == "", "an empty text"
assert swap_halves("ab") == "ba", "two characters swap"
assert swap_halves("abcde") == "deabc", "five characters"
print("ok")
