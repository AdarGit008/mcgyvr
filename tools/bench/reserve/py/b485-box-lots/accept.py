from solution import box_lots

assert box_lots(["a", "b", "c", "d", "e"], 2) == [["a", "b"], ["c", "d"], ["e"]], "a closing lot that does not fill"
assert box_lots(["a", "b", "c", "d"], 2) == [["a", "b"], ["c", "d"]], "every lot fills exactly"
assert box_lots(["a"], 3) == [["a"]], "one entry in a lot that never fills"
assert box_lots(["a", "b", "c"], 1) == [["a"], ["b"], ["c"]], "lots of one"
assert box_lots(["a", "b", "c"], 5) == [["a", "b", "c"]], "a size larger than the run"
assert box_lots([], 2) == [], "a run holding nothing"
print("ok")
