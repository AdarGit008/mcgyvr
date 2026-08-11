from solution import pick_max

assert pick_max([{"a": 1}, {"a": 3}], "a") == {"a": 3}, "the highest wins"
assert pick_max([{"a": 3, "id": 1}, {"a": 3, "id": 2}], "a") == {
    "a": 3,
    "id": 1,
}, "a tie goes to the earlier record"
assert pick_max([], "a") == {}, "no records at all"
assert pick_max([{"b": 1}], "a") == {}, "no record carries the field"
assert pick_max([{"a": 5}], "a") == {"a": 5}, "one record wins by default"
assert pick_max([{"a": 1}, {"a": 2}, {"a": 0}], "a") == {"a": 2}, "the middle one"
print("ok")
