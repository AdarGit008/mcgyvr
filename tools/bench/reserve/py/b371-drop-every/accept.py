from solution import keep_index, drop_every

assert keep_index(1, 2) is True, "the first place survives"
assert keep_index(2, 2) is False, "the second is dropped"
assert drop_every(["a", "b", "c", "d"], 2) == ["a", "c"], "every second goes"
assert drop_every(["a", "b", "c"], 3) == ["a", "b"], "every third goes"
assert drop_every([], 2) == [], "nothing to drop from"
assert drop_every(["a"], 5) == ["a"], "the count never comes round"
print("ok")
