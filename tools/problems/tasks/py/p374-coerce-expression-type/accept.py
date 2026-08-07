from solution import coerce_expression_type


def leaf(name):
    return {"type": name}


def branch(op, left, right):
    return {"op": op, "left": left, "right": right}


assert coerce_expression_type(leaf("tally")) == "tally", "a bare leaf carries its own type"
assert coerce_expression_type(leaf("void")) == "void", "a void leaf is still a void"
assert coerce_expression_type(branch("+", leaf("tally"), leaf("tally"))) == "tally", "two tallies fuse to a tally"
assert coerce_expression_type(branch("+", leaf("tally"), leaf("measure"))) == "measure", "measure is the broader quantity"
assert coerce_expression_type(branch("+", leaf("glyph"), leaf("measure"))) == "glyph", "a glyph swallows a quantity"
assert coerce_expression_type(branch("+", leaf("glyph"), leaf("glyph"))) == "glyph", "two glyphs fuse to a glyph"
assert (
    coerce_expression_type(branch("<", branch("+", leaf("tally"), leaf("measure")), leaf("tally"))) == "flag"
), "ordering two quantities gives a flag"
assert coerce_expression_type(branch("<", leaf("glyph"), leaf("glyph"))) == "flag", "two glyphs may be ordered"
assert coerce_expression_type(branch("=", leaf("flag"), leaf("flag"))) == "flag", "two flags may be matched"
assert coerce_expression_type(branch("=", leaf("void"), leaf("glyph"))) == "flag", "a void matches whatever stands opposite"
assert coerce_expression_type(branch("=", leaf("flag"), leaf("void"))) == "flag", "a void even matches a flag"
assert (
    coerce_expression_type(
        branch("=", branch("+", leaf("tally"), leaf("tally")), branch("+", leaf("measure"), leaf("tally")))
    )
    == "flag"
), "the two sides are worked out before the match"
assert (
    coerce_expression_type(
        branch("+", leaf("glyph"), branch("+", leaf("tally"), branch("+", leaf("measure"), leaf("tally"))))
    )
    == "glyph"
), "a deeper fuse still ends in a glyph"


def chain(levels):
    built = leaf("tally")
    for _ in range(levels):
        built = branch("+", leaf("tally"), built)
    return built


assert coerce_expression_type(chain(11)) == "tally", "eleven branches still fit the cap"


def rejects(value):
    try:
        coerce_expression_type(value)
    except ValueError:
        return True
    return False


assert rejects(chain(12)), "twelve branches nest too deeply"
assert rejects(branch("+", leaf("flag"), leaf("tally"))), "a flag cannot be fused"
assert rejects(branch("+", leaf("void"), leaf("tally"))), "a void cannot be fused"
assert rejects(branch("<", leaf("glyph"), leaf("tally"))), "a glyph has no order against a quantity"
assert rejects(branch("<", leaf("flag"), leaf("flag"))), "flags have no order"
assert rejects(branch("=", leaf("glyph"), leaf("measure"))), "a glyph does not match a quantity"
assert rejects(branch("=", leaf("flag"), leaf("tally"))), "a flag matches nothing but a flag"
assert rejects(leaf("rune")), "a type outside the five is refused"
assert rejects(branch("*", leaf("tally"), leaf("tally"))), "an op outside the three is refused"
assert rejects({"op": "+", "left": leaf("tally")}), "a branch wanting its right is refused"
assert rejects({"type": "tally", "op": "+"}), "a node carrying both is refused"
assert rejects({}), "a node carrying neither is refused"
assert rejects([leaf("tally")]), "a node that is not a mapping is refused"
print("ok")
