from solution import key_of, group_sum

assert key_of({"name": "a"}) == "a", "the name is the group"
assert key_of({}) == "", "no name, no group"
assert group_sum([{"name": "a", "amount": 1}, {"name": "a", "amount": 2}]) == {
    "a": 3
}, "one group totalled"
assert group_sum([{"amount": 5}]) == {}, "a nameless record is passed over"
assert group_sum([]) == {}, "no records at all"
assert group_sum([{"name": "a", "amount": 1}, {"name": "b", "amount": 2}]) == {
    "a": 1,
    "b": 2,
}, "two groups"
print("ok")
