BINDING = {"+": 1, "-": 1, "*": 2, "/": 2}
ATOM = 3


def _binding(node):
    if isinstance(node, int) or isinstance(node, str):
        return ATOM
    return BINDING[node["op"]]


def _render(node):
    if isinstance(node, bool):
        raise ValueError("a node must be a number, a string or a record")
    if isinstance(node, int):
        if node < 0:
            raise ValueError("a literal must be a whole number of zero or more")
        return str(node)
    if isinstance(node, str):
        if node == "" or not all("a" <= ch <= "z" or "A" <= ch <= "Z" for ch in node):
            raise ValueError("a name must be a non-empty run of letters")
        return node
    if not isinstance(node, dict):
        raise ValueError("a node must be a number, a string or a record")
    for field in ("op", "left", "right"):
        if field not in node:
            raise ValueError("a record needs op, left and right")
    if node["op"] not in BINDING:
        raise ValueError("the operator must be one of + - * /")
    power = BINDING[node["op"]]
    left_text = _render(node["left"])
    right_text = _render(node["right"])
    if _binding(node["left"]) < power:
        left_text = "(" + left_text + ")"
    if _binding(node["right"]) <= power:
        right_text = "(" + right_text + ")"
    return left_text + " " + node["op"] + " " + right_text


def print_expr_tree(node):
    return _render(node)
