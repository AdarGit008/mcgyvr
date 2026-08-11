from solution import top_char

assert top_char("aab") == "a", "the commonest character"
assert top_char("ab") == "a", "a tie goes to the first"
assert top_char("") == "", "an empty text"
assert top_char("x") == "x", "a single character"
assert top_char("abbb") == "b", "the later character wins on count"
assert top_char("baab") == "b", "a tie between two, the earlier wins"
print("ok")
