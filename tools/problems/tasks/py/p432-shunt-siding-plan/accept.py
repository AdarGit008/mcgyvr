from solution import plan_shunting


def rejects(arrival, target, depth):
    try:
        plan_shunting(arrival, target, depth)
    except ValueError:
        return True
    return False


assert plan_shunting(["a", "b", "c"], ["a", "b", "c"], 3) == {
    "moves": ["hold a", "place a", "hold b", "place b", "hold c", "place c"],
    "blocked": "",
}, "an order already standing right is held and placed one car at a time"

assert plan_shunting(["a", "b", "c"], ["c", "b", "a"], 3) == {
    "moves": ["hold a", "hold b", "hold c", "place c", "place b", "place a"],
    "blocked": "",
}, "a full reversal fills the siding and empties it"

assert plan_shunting(["a", "b", "c"], ["b", "a", "c"], 2) == {
    "moves": ["hold a", "hold b", "place b", "place a", "hold c", "place c"],
    "blocked": "",
}, "a depth of two is enough when the siding drains between cars"

assert plan_shunting(["a", "b", "c"], ["c", "b", "a"], 2) == {
    "moves": ["hold a", "hold b"],
    "blocked": "full",
}, "the reversal needs a third place on the siding"

assert plan_shunting(["a", "b", "c"], ["c", "a", "b"], 3) == {
    "moves": ["hold a", "hold b", "hold c", "place c"],
    "blocked": "buried:a",
}, "a runs out of arrival cars while sitting under b"

assert plan_shunting(["x"], ["x"], 1) == {
    "moves": ["hold x", "place x"],
    "blocked": "",
}, "one car needs one place on the siding"

assert plan_shunting(["r1", "r2", "r3", "r4"], ["r2", "r4", "r3", "r1"], 4) == {
    "moves": [
        "hold r1",
        "hold r2",
        "place r2",
        "hold r3",
        "hold r4",
        "place r4",
        "place r3",
        "place r1",
    ],
    "blocked": "",
}, "longer codes ride the same drill"

assert rejects("ab", ["a", "b"], 2), "arrival must be a list"
assert rejects(["a"], "a", 2), "target must be a list"
assert rejects([], [], 2), "an empty arrival road is rejected"
assert rejects(["a", ""], ["a", ""], 2), "an empty code is rejected"
assert rejects(["a", 7], ["a", 7], 2), "a non-string code is rejected"
assert rejects(["a", "a"], ["a", "a"], 2), "a repeated arrival code is rejected"
assert rejects(["a", "b"], ["a", "c"], 2), "different cars are rejected"
assert rejects(["a", "b"], ["a"], 2), "a short target is rejected"
assert rejects(["a", "b"], ["a", "b"], 0), "a depth below one is rejected"
assert rejects(["a", "b"], ["a", "b"], 1.5), "a fractional depth is rejected"
print("ok")
