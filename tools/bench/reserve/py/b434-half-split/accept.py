from solution import half_split

assert half_split(["a", "b"]) == [["a"], ["b"]], "an even split"
assert half_split(["a", "b", "c"]) == [
    ["a", "b"],
    ["c"],
], "the spare goes to the first half"
assert half_split([]) == [[], []], "two empty halves"
assert half_split(["a"]) == [["a"], []], "one entry is all first half"
assert half_split(["a", "b", "c", "d"]) == [["a", "b"], ["c", "d"]], "four split evenly"
assert half_split(["a", "b", "c", "d", "e"]) == [["a", "b", "c"], ["d", "e"]], "five"
print("ok")
