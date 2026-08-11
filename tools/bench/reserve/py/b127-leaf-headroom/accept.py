from solution import leaf_headroom

assert leaf_headroom({"limit": 100, "children": {"api": {"limit": 40, "used": 15}}}) == {
    "api": 25
}, "the leaf's own limit binds"
assert leaf_headroom({"limit": 30, "children": {"api": {"limit": 40, "used": 5}}}) == {
    "api": 25
}, "the root's limit binds"
assert leaf_headroom(
    {
        "limit": 100,
        "children": {"a": {"limit": 60, "used": 20}, "b": {"limit": 80, "used": 50}},
    }
) == {"a": 30, "b": 30}, "a sibling's burn counts against the shared root"
assert leaf_headroom(
    {
        "limit": 50,
        "children": {"team": {"limit": 30, "children": {"job": {"limit": 20, "used": 5}}}},
    }
) == {"team/job": 15}, "nested groups join the path with a slash"
assert leaf_headroom({"limit": 10, "children": {"a": {"limit": 8, "used": 9}}}) == {
    "a": 0
}, "an overspent leaf floors at zero"
assert leaf_headroom({"limit": 5, "children": {}}) == {}, "a childless root yields no leaves"
assert leaf_headroom(
    {
        "limit": 20,
        "children": {"idle": {"limit": 5, "children": {}}, "live": {"limit": 6, "used": 2}},
    }
) == {"live": 4}, "an empty subgroup contributes no leaves"
assert leaf_headroom(
    {
        "limit": 90,
        "children": {
            "org": {
                "limit": 60,
                "children": {"app": {"limit": 40, "children": {"key": {"limit": 12, "used": 2}}}},
            }
        },
    }
) == {"org/app/key": 10}, "a deep path names every enclosing group"


def rejects(tree):
    try:
        leaf_headroom(tree)
    except Exception:
        return True
    return False


assert rejects("nope"), "a non-object root is rejected"
assert rejects({"limit": 5, "used": 1}), "a leaf root is rejected"
assert rejects({"children": {}}), "a missing limit is rejected"
assert rejects({"limit": -5, "children": {}}), "a negative limit is rejected"
assert rejects({"limit": 10, "used": 3, "children": {}}), "a group carrying used is rejected"
assert rejects({"limit": 10, "children": "many"}), "non-mapping children are rejected"
assert rejects({"limit": 10, "children": {"a": {"limit": 5}}}), "a leaf without used is rejected"
assert rejects({"limit": 10, "children": {"a": {"limit": 5, "used": -1}}}), "negative used is rejected"
assert rejects({"limit": 10, "children": {"": {"limit": 5, "used": 0}}}), "an empty child name is rejected"
assert rejects({"limit": 10, "children": {"a/b": {"limit": 5, "used": 0}}}), "a slash in a child name is rejected"
print("ok")
