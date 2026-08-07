from solution import tree_delta


def leaf(name, value):
    return {"name": name, "value": value, "children": []}


assert tree_delta(leaf("root", 1), leaf("root", 1)) == [], (
    "identical trees produce no ops"
)

assert tree_delta(leaf("root", 1), leaf("root", 5)) == [
    {"op": "change", "path": "root", "from": 1, "to": 5}
], "root value change"

before_tree = {
    "name": "r",
    "value": 0,
    "children": [
        {"name": "a", "value": 1, "children": [leaf("x", 7)]},
        leaf("b", 2),
    ],
}
after_tree = {
    "name": "r",
    "value": 0,
    "children": [
        {"name": "a", "value": 1, "children": []},
        {"name": "c", "value": 3, "children": [leaf("y", 4)]},
    ],
}
assert tree_delta(before_tree, after_tree) == [
    {"op": "remove", "path": "r/a/x"},
    {"op": "add", "path": "r/c", "value": 3},
    {"op": "add", "path": "r/c/y", "value": 4},
    {"op": "remove", "path": "r/b"},
], "adds are preorder per node, removes are one per subtree"

assert tree_delta(
    {"name": "n", "value": 1, "children": [leaf("k", 2)]},
    {"name": "n", "value": 9, "children": [leaf("k", 3), leaf("m", 4)]},
) == [
    {"op": "change", "path": "n", "from": 1, "to": 9},
    {"op": "change", "path": "n/k", "from": 2, "to": 3},
    {"op": "add", "path": "n/m", "value": 4},
], "a node's change precedes its child ops"


def rejects(before, after):
    try:
        tree_delta(before, after)
    except ValueError:
        return True
    return False


assert rejects(leaf("a", 1), leaf("b", 1)), "differing root names are rejected"
assert rejects(
    {"name": "r", "value": 0, "children": [leaf("d", 1), leaf("d", 2)]},
    leaf("r", 0),
), "duplicate sibling names in before are rejected"
assert rejects(
    leaf("r", 0),
    {"name": "r", "value": 0, "children": [leaf("d", 1), leaf("d", 2)]},
), "duplicate sibling names in after are rejected"

print("ok")
