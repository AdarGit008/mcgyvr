from solution import zero_tail

assert zero_tail(1200) == 2, "two zeros at the end"
assert zero_tail(5) == 0, "no zeros at all"
assert zero_tail(0) == 1, "zero counts as one"
assert zero_tail(100000) == 5, "a long tail"
assert zero_tail(101) == 0, "an inner zero does not count"
assert zero_tail(10) == 1, "one zero"
print("ok")
