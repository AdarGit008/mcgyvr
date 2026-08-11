from solution import crate_fill, crate_total

assert crate_fill(7, 3) == [3, 2, 2], "the leftover leads"
assert crate_fill(6, 3) == [2, 2, 2], "an even split"
assert crate_fill(2, 5) == [1, 1, 0, 0, 0], "more crates than items"
assert crate_fill(5, 0) == [], "zero crates hold nothing"
assert crate_total([3, 2, 2]) == 7, "the sizes add back up"
assert crate_total([]) == 0, "nothing sums to nothing"
print("ok")
