from solution import rollup_totals

assert rollup_totals(
    {
        "r": {"value": 1, "parent": ""},
        "a": {"value": 2, "parent": "r"},
        "b": {"value": 4, "parent": "a"},
    }
) == {"r": 7, "a": 6, "b": 4}, "a grandchild counts into the root"
assert rollup_totals(
    {
        "r": {"value": 1, "parent": ""},
        "a": {"value": 2, "parent": "r"},
        "b": {"value": 3, "parent": "r"},
        "c": {"value": 5, "parent": "a"},
    }
) == {"r": 11, "a": 7, "b": 3, "c": 5}, "branches roll up separately"
assert rollup_totals({"solo": {"value": 9, "parent": ""}}) == {"solo": 9}, (
    "a lone root keeps its own value"
)
assert rollup_totals(
    {
        "r": {"value": 1, "parent": ""},
        "a": {"value": 1, "parent": "r"},
        "b": {"value": 1, "parent": "a"},
        "c": {"value": 1, "parent": "b"},
    }
) == {"r": 4, "a": 3, "b": 2, "c": 1}, "four levels accumulate"


def rejects(nodes):
    try:
        rollup_totals(nodes)
    except ValueError:
        return True
    return False


assert rejects({"r": {"value": 1, "parent": "ghost"}}), "unknown parent rejected"
assert rejects(
    {"r": {"value": 1, "parent": ""}, "s": {"value": 1, "parent": ""}}
), "two roots rejected"
assert rejects(
    {"a": {"value": 1, "parent": "b"}, "b": {"value": 1, "parent": "a"}}
), "no root rejected"
assert rejects(
    {
        "r": {"value": 1, "parent": ""},
        "a": {"value": 1, "parent": "b"},
        "b": {"value": 1, "parent": "a"},
    }
), "nodes off the root rejected"
print("ok")
