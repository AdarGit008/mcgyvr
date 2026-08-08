from solution import print_expr_tree


def node(op, left, right):
    return {"op": op, "left": left, "right": right}


assert (
    print_expr_tree(node("*", node("+", "a", "b"), "c")) == "(a + b) * c"
), "a loose left child under a tight parent needs brackets"
assert (
    print_expr_tree(node("+", node("*", "a", "b"), "c")) == "a * b + c"
), "a tight left child under a loose parent needs none"
assert print_expr_tree(42) == "42", "a literal renders as its digits"
assert print_expr_tree("total") == "total", "a name renders as itself"
assert print_expr_tree(node("+", "a", "b")) == "a + b", "a plain pair takes no brackets"
assert (
    print_expr_tree(node("-", "a", node("-", "b", "c"))) == "a - (b - c)"
), "an equally tight right child is bracketed because the operators gather left"
assert (
    print_expr_tree(node("-", node("-", "a", "b"), "c")) == "a - b - c"
), "an equally tight left child is left bare"
assert (
    print_expr_tree(node("/", "a", node("*", "b", "c"))) == "a / (b * c)"
), "division brackets a multiplying right side"
assert (
    print_expr_tree(node("*", node("/", "a", "b"), "c")) == "a / b * c"
), "division on the left of a product stands unbracketed"
assert (
    print_expr_tree(node("+", node("+", "a", "b"), node("+", "c", "d")))
    == "a + b + (c + d)"
), "only the right of two equal sums is bracketed"
assert (
    print_expr_tree(node("*", node("+", 1, 2), node("-", "x", 3))) == "(1 + 2) * (x - 3)"
), "both sides may need brackets at once"
assert (
    print_expr_tree(node("+", "a", node("*", "b", node("+", "c", "d"))))
    == "a + b * (c + d)"
), "brackets are added only where the depth demands them"


def rejects(tree):
    try:
        print_expr_tree(tree)
    except ValueError:
        return True
    return False


assert rejects(node("%", "a", "b")), "an unknown operator is rejected"
assert rejects({"op": "+", "left": "a"}), "a record missing a side is rejected"
assert rejects(-1), "a negative literal is rejected"
assert rejects(1.5), "a fractional literal is rejected"
assert rejects("a1"), "a name with a digit is rejected"
assert rejects(""), "an empty name is rejected"
assert rejects(None), "a missing node is rejected"
assert rejects(["+", "a", "b"]), "a node given as a list is rejected"
assert rejects(node("+", "a", -2)), "a bad literal deep in the tree is rejected"
print("ok")
