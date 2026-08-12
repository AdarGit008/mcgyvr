from solution import crate_stack

assert crate_stack(["short", "short", "tall"], 9) == ["short", "short", "tall"], "the pile reaches the ceiling exactly"
assert crate_stack(["tall", "tall"], 9) == ["tall"], "the second would pass the ceiling"
assert crate_stack(["tall", "short", "short"], 7) == ["tall", "short"], "stopping part way"
assert crate_stack(["odd", "short"], 5) == ["odd", "short"], "an unnamed kind takes the middle height"
assert crate_stack(["short"], 1) == [], "the first crate already passes it"
assert crate_stack([], 5) == [], "an empty run"
print("ok")
