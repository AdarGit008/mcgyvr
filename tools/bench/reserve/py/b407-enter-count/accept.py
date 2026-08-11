from solution import enter_count

assert enter_count(["a", "a", "b", "a"], "a") == 2, "held then re-entered"
assert enter_count(["a"], "a") == 1, "entered at the start"
assert enter_count([], "a") == 0, "no states at all"
assert enter_count(["b"], "a") == 0, "never entered"
assert enter_count(["a", "b", "a", "b", "a"], "a") == 3, "entered three times"
assert enter_count(["a", "a"], "a") == 1, "holding is not re-entering"
print("ok")
