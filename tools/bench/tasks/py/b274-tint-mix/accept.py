from solution import tint_mix

assert tint_mix(100, 10, 100, 20) == 15, "equal volumes meet in the middle"
assert tint_mix(0, 0, 0, 0) == 0, "two empty tins"
assert tint_mix(50, 10, 150, 50) == 40, "the larger tin pulls harder"
assert tint_mix(100, 10, 0, 90) == 10, "an empty second tin changes nothing"
assert tint_mix(3, 10, 4, 20) == 15, "rounded down from a fraction"
assert tint_mix(1, 99, 1, 100) == 99, "a half rounds down"
print("ok")
