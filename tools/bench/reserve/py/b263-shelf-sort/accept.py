from solution import shelf_sort

assert shelf_sort(["row9", "row10"]) == ["row9", "row10"], "already in order"
assert shelf_sort(["row10", "row9"]) == ["row9", "row10"], "ten follows nine"
assert shelf_sort(["bin2", "bin1"]) == ["bin1", "bin2"], "a plain swap"
assert shelf_sort([]) == [], "nothing to sort"
assert shelf_sort(["a1"]) == ["a1"], "a single label"
assert shelf_sort(["x3", "y3", "w3"]) == [
    "x3",
    "y3",
    "w3",
], "equal numbers keep their arrival order"
print("ok")
