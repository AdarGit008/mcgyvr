from solution import live_count, live_next

assert live_count([True, False, True]) == 2, "two of three are alive"
assert live_count([]) == 0, "no neighbours at all"
assert live_next(True, [True, True]) is True, "two neighbours keep it alive"
assert live_next(True, [True]) is False, "one is too lonely"
assert live_next(False, [True, True, True]) is True, "three bring it to life"
assert live_next(False, [True, True]) is False, "two are not enough to start"
assert live_next(True, [True, True, True, True]) is False, "four is crowded"
print("ok")
