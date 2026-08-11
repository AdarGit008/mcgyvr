from solution import add_one, merge_tally

assert add_one({"a": 1}, "a", 2) == {"a": 3}, "added to an existing name"
assert add_one({}, "a", 1) == {"a": 1}, "a new name starts at nothing"
assert merge_tally({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}, "no name is shared"
assert merge_tally({"a": 1}, {"a": 2}) == {"a": 3}, "a shared name adds up"
assert merge_tally({}, {}) == {}, "two empty tallies"

source = {"a": 1}
add_one(source, "a", 5)
assert source == {"a": 1}, "the tally it was given is unchanged"
print("ok")
