TYPES = ["tally", "measure", "glyph", "flag", "void"]
DEPTH_CAP = 12


def _fuse(left, right):
    if left == "void" or right == "void":
        raise ValueError("a void cannot be fused")
    if left == "flag" or right == "flag":
        raise ValueError("a flag cannot be fused")
    if left == "glyph" or right == "glyph":
        return "glyph"
    return "measure" if left == "measure" or right == "measure" else "tally"


def _order(left, right):
    if left == "void" or right == "void":
        raise ValueError("a void has no order")
    if left == "flag" or right == "flag":
        raise ValueError("a flag has no order")
    if left == "glyph" or right == "glyph":
        if left != right:
            raise ValueError("a glyph has no order against a quantity")
        return "flag"
    return "flag"


def _match(left, right):
    if left == "void" or right == "void":
        return "flag"
    if left == "flag" or right == "flag":
        if left != right:
            raise ValueError("a flag matches nothing but another flag")
        return "flag"
    if left == "glyph" or right == "glyph":
        if left != right:
            raise ValueError("a glyph does not match a quantity")
        return "flag"
    return "flag"


def _walk(node, depth):
    if depth > DEPTH_CAP:
        raise ValueError("the expression nests deeper than " + str(DEPTH_CAP) + " nodes")
    if not isinstance(node, dict):
        raise ValueError("every node must be a mapping")
    leaf = "type" in node
    branch = "op" in node
    if leaf == branch:
        raise ValueError("a node carries either a type or an op, never both or neither")
    if leaf:
        name = node["type"]
        if not isinstance(name, str) or name not in TYPES:
            raise ValueError("a leaf must name one of the five types")
        return name
    op = node["op"]
    if op not in ("+", "<", "="):
        raise ValueError("an op must be one of +, < and =")
    if "left" not in node or "right" not in node:
        raise ValueError("a branch must carry a left and a right")
    left = _walk(node["left"], depth + 1)
    right = _walk(node["right"], depth + 1)
    if op == "+":
        return _fuse(left, right)
    if op == "<":
        return _order(left, right)
    return _match(left, right)


def coerce_expression_type(node: dict) -> str:
    return _walk(node, 1)
