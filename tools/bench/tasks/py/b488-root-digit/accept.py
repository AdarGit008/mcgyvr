from solution import root_digit

assert root_digit(38) == 2, "the folding runs more than once"
assert root_digit(99) == 9, "a second fold is needed"
assert root_digit(12345) == 6, "a longer count folds twice"
assert root_digit(10) == 1, "a count that folds to one figure at once"
assert root_digit(9) == 9, "a count already standing as one figure"
assert root_digit(0) == 0, "a count of nothing"
print("ok")
