from solution import gauge_macro_depth

sheet = [
    {"name": "leaf", "arity": 0, "calls": []},
    {"name": "wrap", "arity": 1, "calls": [["leaf", 0]]},
    {"name": "outer", "arity": 0, "calls": [["wrap", 1], ["leaf", 0]]},
    {"name": "ping", "arity": 0, "calls": [["pong", 0]]},
    {"name": "pong", "arity": 0, "calls": [["ping", 0]]},
    {"name": "lead", "arity": 0, "calls": [["ping", 0]]},
]

assert gauge_macro_depth(sheet, 5) == [
    "lead cyclic",
    "leaf 0",
    "outer 2",
    "ping cyclic",
    "pong cyclic",
    "wrap 1",
], "depths, a two-macro loop, and a macro that reaches it"

assert gauge_macro_depth(sheet, 1) == [
    "lead cyclic",
    "leaf 0",
    "outer over",
    "ping cyclic",
    "pong cyclic",
    "wrap 1",
], "a bound of one puts only the deepest over"

assert gauge_macro_depth(sheet, 0) == [
    "lead cyclic",
    "leaf 0",
    "outer over",
    "ping cyclic",
    "pong cyclic",
    "wrap over",
], "a bound of nought leaves only the leaf inside it"

assert gauge_macro_depth([{"name": "solo", "arity": 0, "calls": [["solo", 0]]}], 9) == [
    "solo cyclic"
], "a macro calling itself never settles"

assert gauge_macro_depth(
    [
        {"name": "leaf", "arity": 0, "calls": []},
        {"name": "twin", "arity": 0, "calls": [["leaf", 0], ["leaf", 0]]},
    ],
    4,
) == ["leaf 0", "twin 1"], "calling one name twice is still one step"

assert gauge_macro_depth([], 3) == [], "no macros gives no lines"

assert gauge_macro_depth(
    [
        {"name": "a1", "arity": 2, "calls": [["b2", 1]]},
        {"name": "b2", "arity": 1, "calls": [["c3", 0]]},
        {"name": "c3", "arity": 0, "calls": []},
    ],
    2,
) == ["a1 2", "b2 1", "c3 0"], "a chain of three settles at rising depths"


def rejects(*args):
    try:
        gauge_macro_depth(*args)
    except ValueError:
        return True
    return False


assert rejects("no", 1), "the macros must be a list"
assert rejects([3], 1), "a macro must be a record"
assert rejects([{"name": "a", "arity": 0}], 1), "a macro missing a key is refused"
assert rejects([{"name": "9a", "arity": 0, "calls": []}], 1), "a name opening with a digit is refused"
assert rejects(
    [{"name": "a", "arity": 0, "calls": []}, {"name": "a", "arity": 1, "calls": []}], 1
), "a repeated name is refused"
assert rejects([{"name": "a", "arity": 10, "calls": []}], 1), "an arity of ten is refused"
assert rejects([{"name": "a", "arity": 0, "calls": "no"}], 1), "calls that are not a list are refused"
assert rejects([{"name": "a", "arity": 0, "calls": [["b"]]}], 1), "a one-entry call is refused"
assert rejects([{"name": "a", "arity": 0, "calls": [["ghost", 0]]}], 1), "an undeclared callee is refused"
assert rejects(
    [{"name": "a", "arity": 0, "calls": [["b", 2]]}, {"name": "b", "arity": 1, "calls": []}], 1
), "a mismatched argument count is refused"
assert rejects([{"name": "a", "arity": 0, "calls": [["a", -1]]}], 1), "a negative argument count is refused"
assert rejects([{"name": "a", "arity": 0, "calls": []}], -2), "a negative bound is refused"
print("ok")
