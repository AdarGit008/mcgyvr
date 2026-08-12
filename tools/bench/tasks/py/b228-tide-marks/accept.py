from solution import tide_marks

assert tide_marks([1, 3, 2]) == [1], "one interior peak"
assert tide_marks([1, 2, 3]) == [], "a rising run has no peak"
assert tide_marks([3, 2, 1]) == [], "a falling run has no peak"
assert tide_marks([1, 3, 2, 5, 4]) == [1, 3], "peaks in increasing order"
assert tide_marks([2, 2, 2]) == [], "a flat run is not a peak"
assert tide_marks([1, 3, 3, 2]) == [], "a plateau is not a peak"
assert tide_marks([]) == [], "no readings, no peaks"
print("ok")
