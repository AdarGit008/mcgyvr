from solution import merge_three_way

base = {"host": "a", "port": "80", "mode": "dev"}

assert merge_three_way(
    base,
    {"host": "a", "port": "81", "mode": "dev"},
    {"host": "a", "port": "80", "mode": "prod"},
) == {
    "merged": {"host": "a", "mode": "prod", "port": "81"},
    "conflicts": [],
}, "disjoint edits both carry"
assert merge_three_way(
    base,
    {"host": "a", "port": "81", "mode": "dev"},
    {"host": "a", "port": "82", "mode": "dev"},
) == {
    "merged": {"host": "a", "mode": "dev", "port": "80"},
    "conflicts": ["port"],
}, "rival values conflict and the ancestor value stays"
assert merge_three_way(
    base,
    {"host": "a", "port": "90", "mode": "dev"},
    {"host": "a", "port": "90", "mode": "dev"},
) == {
    "merged": {"host": "a", "mode": "dev", "port": "90"},
    "conflicts": [],
}, "the identical edit on both sides is clean"
assert merge_three_way(base, {"port": "80", "mode": "dev"}, base) == {
    "merged": {"mode": "dev", "port": "80"},
    "conflicts": [],
}, "a one-sided removal carries"
assert merge_three_way(
    base,
    {"port": "80", "mode": "dev"},
    {"host": "b", "port": "80", "mode": "dev"},
) == {
    "merged": {"host": "a", "mode": "dev", "port": "80"},
    "conflicts": ["host"],
}, "removal against alteration conflicts and the ancestor entry stays"
assert merge_three_way(
    base, {"port": "80", "mode": "dev"}, {"port": "80", "mode": "dev"}
) == {
    "merged": {"mode": "dev", "port": "80"},
    "conflicts": [],
}, "both sides removing is clean"
assert merge_three_way({}, {"fresh": "x"}, {}) == {
    "merged": {"fresh": "x"},
    "conflicts": [],
}, "a one-sided addition carries"
assert merge_three_way({}, {"fresh": "x"}, {"fresh": "y"}) == {
    "merged": {},
    "conflicts": ["fresh"],
}, "rival additions conflict and stay absent"
assert merge_three_way(
    {"z": "1", "a": "1"}, {"z": "2", "a": "2"}, {"z": "3", "a": "3"}
) == {
    "merged": {"a": "1", "z": "1"},
    "conflicts": ["a", "z"],
}, "conflicts come out in ascending key order"
assert merge_three_way(base, base, base) == {
    "merged": {"host": "a", "mode": "dev", "port": "80"},
    "conflicts": [],
}, "no edits, no conflicts"


def rejects(*args):
    try:
        merge_three_way(*args)
    except ValueError:
        return True
    return False


assert rejects(base, "nope", base), "a non-mapping side is rejected"
assert rejects(base, {"port": 80}, base), "a non-string value is rejected"
print("ok")
