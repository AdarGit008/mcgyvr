from solution import bill_split

assert bill_split(100, 4) == [25, 25, 25, 25], "an even bill"
assert bill_split(101, 4) == [26, 25, 25, 25], "the first takes the penny"
assert bill_split(10, 3) == [4, 3, 3], "two pennies over"
assert bill_split(5, 1) == [5], "one diner pays it all"
assert bill_split(0, 2) == [0, 0], "nothing to pay"
assert bill_split(7, 2) == [4, 3], "an odd bill between two"
print("ok")
