from solution import slot_pack

assert slot_pack(["a", "b", "c", "d", "e"], 2) == [
    ["a", "b"],
    ["c", "d"],
    ["e"],
], "a short final slot"
assert slot_pack(["a", "b", "c"], 3) == [["a", "b", "c"]], "one exact slot"
assert slot_pack([], 2) == [], "nothing to pack"
assert slot_pack(["a", "b"], 1) == [["a"], ["b"]], "one item per slot"
assert slot_pack(["a", "b"], 5) == [["a", "b"]], "capacity to spare"
assert slot_pack(["x", "y", "z"], 2) == [["x", "y"], ["z"]], "order is kept"
print("ok")
