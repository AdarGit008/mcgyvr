from solution import tally_marks

assert tally_marks("abc") == 6, "no mark follows its own kind"
assert tally_marks("aab") == 5, "one mark doubles"
assert tally_marks("bb") == 6, "a weightier mark doubles"
assert tally_marks("aaa") == 5, "each following mark doubles the usual value"
assert tally_marks("z") == 0, "a mark worth nothing"
assert tally_marks("") == 0, "a line holding no marks"
print("ok")
