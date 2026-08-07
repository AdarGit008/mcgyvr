POWER = {
    "or": 1,
    "and": 2,
    "+": 3,
    "-": 3,
    "*": 4,
    "/": 4,
    "^": 6,
}
NEGATE = 5
ALONE = 9


def _lowercase_word(value):
    return (
        isinstance(value, str)
        and value != ""
        and all("a" <= letter <= "z" for letter in value)
    )


def _power(node):
    if isinstance(node, int) or isinstance(node, str):
        return ALONE
    if "op" in node:
        return POWER[node["op"]]
    if "negate" in node:
        return NEGATE
    return ALONE


def _show(node):
    if isinstance(node, bool):
        raise ValueError("a node must be a number, a word or a record")
    if isinstance(node, int):
        if node < 0:
            raise ValueError("a number must be whole and not negative")
        return str(node)
    if isinstance(node, str):
        if not _lowercase_word(node):
            raise ValueError("a word must be a non-empty run of lowercase letters")
        return node
    if not isinstance(node, dict):
        raise ValueError("a node must be a number, a word or a record")
    if "op" in node:
        if "left" not in node or "right" not in node:
            raise ValueError("a record carrying op needs left and right")
        if node["op"] not in POWER:
            raise ValueError("the operator is outside the seven")
        here = POWER[node["op"]]
        rightward = node["op"] == "^"
        left_text = _show(node["left"])
        right_text = _show(node["right"])
        left_power = _power(node["left"])
        right_power = _power(node["right"])
        if left_power < here or (left_power == here and rightward):
            left_text = "(" + left_text + ")"
        if right_power < here or (right_power == here and not rightward):
            right_text = "(" + right_text + ")"
        return left_text + " " + node["op"] + " " + right_text
    if "negate" in node:
        inner = node["negate"]
        text = _show(inner)
        doubled = isinstance(inner, dict) and "negate" in inner
        if _power(inner) < NEGATE or doubled:
            return "-(" + text + ")"
        return "-" + text
    if "call" in node:
        if not _lowercase_word(node["call"]):
            raise ValueError("a call word must be a run of lowercase letters")
        if "args" not in node or not isinstance(node["args"], list):
            raise ValueError("a call needs a list under args")
        return node["call"] + "(" + ", ".join(_show(one) for one in node["args"]) + ")"
    raise ValueError("a record must carry op, negate or call")


def print_operator_tree(node):
    return _show(node)
