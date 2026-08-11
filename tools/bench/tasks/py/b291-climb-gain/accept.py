from solution import leg_gain, climb_gain

assert leg_gain(10, 15) == 5, "a rise is a gain"
assert leg_gain(15, 10) == 0, "a fall gains nothing"
assert leg_gain(4, 4) == 0, "level ground gains nothing"
assert climb_gain([1, 4, 9]) == 8, "two rises add up"
assert climb_gain([9, 2, 6]) == 4, "only the rise counts"
assert climb_gain([5, 5, 5]) == 0, "a flat walk"
assert climb_gain([7]) == 0, "one height is not a leg"
assert climb_gain([]) == 0, "no heights, no gain"
print("ok")
