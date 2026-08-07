from solution import print_operator_tree


def op(name, left, right):
    return {"op": name, "left": left, "right": right}


def neg(inner):
    return {"negate": inner}


def call(word, args):
    return {"call": word, "args": args}


assert (
    print_operator_tree(op("+", op("*", "a", "b"), "c")) == "a * b + c"
), "a tighter operand under a looser operator stands bare"
assert (
    print_operator_tree(op("^", "a", op("^", "b", "c"))) == "a ^ b ^ c"
), "the gathering side of ^ needs no parentheses"
assert (
    print_operator_tree(op("^", op("^", "a", "b"), "c")) == "(a ^ b) ^ c"
), "the other side of ^ does"
assert (
    print_operator_tree(neg(op("+", "a", "b"))) == "-(a + b)"
), "a sum under a minus sign is parenthesised"
assert (
    print_operator_tree(op("^", neg("a"), "b")) == "(-a) ^ b"
), "a negate under ^ binds too loosely to stand bare"
assert (
    print_operator_tree(neg(op("^", "a", "b"))) == "-a ^ b"
), "a power under a minus sign binds tightly enough to stand bare"
assert (
    print_operator_tree(neg(neg("a"))) == "-(-a)"
), "a negate directly under a negate is always parenthesised"
assert (
    print_operator_tree(op("and", op("or", "p", "q"), "r")) == "(p or q) and r"
), "or is looser than and and must be fenced off"
assert (
    print_operator_tree(op("or", "p", op("and", "q", "r"))) == "p or q and r"
), "and under or needs nothing"
assert (
    print_operator_tree(op("or", "p", op("or", "q", "r"))) == "p or (q or r)"
), "equal power on the non-gathering side takes parentheses"
assert (
    print_operator_tree(call("max", ["a", op("+", "b", 1), neg("c")]))
    == "max(a, b + 1, -c)"
), "arguments are separated by a comma and a space and never fenced"
assert print_operator_tree(call("now", [])) == "now()", "a call may take nothing"
assert (
    print_operator_tree(op("*", call("max", ["a", "b"]), "c")) == "max(a, b) * c"
), "a call stands alone and binds tightest"
assert (
    print_operator_tree(op("-", "a", op("+", "b", "c"))) == "a - (b + c)"
), "a sum on the right of a subtraction is fenced off"
assert (
    print_operator_tree(op("/", op("*", "a", "b"), op("/", "c", "d")))
    == "a * b / (c / d)"
), "equal power is bare on the left and fenced on the right"
assert (
    print_operator_tree(op("and", neg(op("or", "a", "b")), op("^", "c", neg("d"))))
    == "-(a or b) and c ^ (-d)"
), "each depth decides its own parentheses"
assert print_operator_tree(op("+", 0, 12)) == "0 + 12", "zero is an ordinary number"


def rejects(tree):
    try:
        print_operator_tree(tree)
    except ValueError:
        return True
    return False


assert rejects(op("%", "a", "b")), "an operator outside the seven is rejected"
assert rejects({"op": "+", "left": "a"}), "a record missing right is rejected"
assert rejects({"size": 3}), "a record carrying none of the three is rejected"
assert rejects({"call": "max", "args": "a"}), "args given as text is rejected"
assert rejects(call("Max", [])), "an upper-case call word is rejected"
assert rejects("a1"), "a word with a digit is rejected"
assert rejects(-3), "a negative number is rejected"
assert rejects(neg(None)), "a missing operand is rejected"
assert rejects(["+", "a", "b"]), "a node given as a list is rejected"
print("ok")
