from solution import swap_keys

assert swap_keys({"ann": "a1", "bob": "b2"}) == {
    "a1": "ann",
    "b2": "bob",
}, "each code finds its name"
assert swap_keys({"zoe": "x", "amy": "x"}) == {"x": "amy"}, "the first name wins"
assert swap_keys({"ann": ""}) == {}, "an empty code is left out"
assert swap_keys({}) == {}, "nothing maps to nothing"
assert swap_keys({"bob": "b2", "ann": "a1"}) == {
    "a1": "ann",
    "b2": "bob",
}, "the order it arrives in does not matter"
assert swap_keys({"ann": "a1", "bob": "a1", "cat": "c3"}) == {
    "a1": "ann",
    "c3": "cat",
}, "a shared code keeps one name"
print("ok")
