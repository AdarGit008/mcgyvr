from solution import tally_bar

assert tally_bar(3, 5) == "###", "a bar well inside the width"
assert tally_bar(5, 5) == "#####", "a bar exactly on the width"
assert tally_bar(9, 5) == "####>", "a cut bar is marked"
assert tally_bar(0, 5) == "", "nothing to draw"
assert tally_bar(1, 5) == "#", "a bar of one"
assert tally_bar(6, 2) == "#>", "a short width"
print("ok")
