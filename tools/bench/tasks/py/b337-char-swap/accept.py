from solution import swap_pair, swap_all

assert swap_pair("a", "b") == "ba", "two characters turn round"
assert swap_all("abcd") == "badc", "two whole pairs"
assert swap_all("abc") == "bac", "the odd one stays put"
assert swap_all("") == "", "nothing to swap"
assert swap_all("a") == "a", "one character is already odd"
assert swap_all("ab") == "ba", "a single pair"
print("ok")
