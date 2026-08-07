from solution import first_broken_rule


def node(key, count, left=None, right=None):
    return {"key": key, "count": count, "left": left, "right": right}


def leaf(key, count=1):
    return node(key, count)


def rejects(root):
    try:
        first_broken_rule(root)
    except ValueError:
        return True
    return False


assert first_broken_rule(leaf(5)) == {
    "path": "",
    "rule": "sound",
}, "a lone node breaks nothing"

assert first_broken_rule(node(10, 4, node(5, 2, None, leaf(7)), leaf(20))) == {
    "path": "",
    "rule": "sound",
}, "a well-formed little tree breaks nothing"

assert first_broken_rule(leaf(5, 2)) == {
    "path": "root",
    "rule": "count",
}, "a lone node claiming two is caught"

assert first_broken_rule(node(5, 2, leaf(7))) == {
    "path": "root",
    "rule": "order",
}, "a left child above its parent breaks order"

assert first_broken_rule(node(5, 2, leaf(5))) == {
    "path": "root",
    "rule": "order",
}, "an equal key on the left is not strictly smaller"

assert first_broken_rule(node(10, 4, node(5, 2, None, leaf(12)), leaf(20))) == {
    "path": "root",
    "rule": "order",
}, "order looks the whole subtree down, not only at the children"

assert first_broken_rule(node(10, 4, node(5, 2, None, leaf(3)), leaf(20))) == {
    "path": "root/L",
    "rule": "order",
}, "a sound root does not excuse a broken child"

assert first_broken_rule(node(10, 3, node(5, 2, leaf(1)))) == {
    "path": "root",
    "rule": "balance",
}, "one side two deeper than the other breaks balance"

assert first_broken_rule(node(10, 3, leaf(5), leaf(20, 2))) == {
    "path": "root/R",
    "rule": "count",
}, "a child overstating its subtree is caught"

assert first_broken_rule(node(5, 3, node(9, 2, leaf(8)))) == {
    "path": "root",
    "rule": "order",
}, "order is tested before balance at the same node"

assert first_broken_rule(node(10, 99, node(5, 2, leaf(1)))) == {
    "path": "root",
    "rule": "balance",
}, "balance is tested before count at the same node"

assert first_broken_rule(
    node(10, 5, node(5, 2, None, leaf(3)), node(20, 2, leaf(25)))
) == {"path": "root/L", "rule": "order"}, "the left side is walked before the right"

assert rejects(None), "an absent root is rejected"
assert rejects(7), "a root that is not a mapping is rejected"
assert rejects(
    {"count": 1, "left": None, "right": None}
), "a node with no key entry is rejected"
assert rejects(node("5", 1)), "a key that is not a whole number is rejected"
assert rejects(node(5, 0)), "a count of zero is rejected"
assert rejects({"key": 5, "count": 1, "right": None}), "no left entry is rejected"
assert rejects(node(5, 2, 3)), "a side that is neither a node nor nothing is rejected"

print("ok")
