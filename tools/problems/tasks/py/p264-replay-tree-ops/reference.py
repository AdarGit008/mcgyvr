import re


def graft(knot, value):
    if knot is None:
        return {"value": value, "left": None, "right": None}
    if value < knot["value"]:
        knot["left"] = graft(knot["left"], value)
    elif value > knot["value"]:
        knot["right"] = graft(knot["right"], value)
    return knot


def excise(knot, value):
    if knot is None:
        raise ValueError("cannot drop a value the index does not hold")
    if value < knot["value"]:
        knot["left"] = excise(knot["left"], value)
        return knot
    if value > knot["value"]:
        knot["right"] = excise(knot["right"], value)
        return knot
    if knot["left"] is None:
        return knot["right"]
    if knot["right"] is None:
        return knot["left"]
    highest = knot["left"]
    while highest["right"] is not None:
        highest = highest["right"]
    knot["value"] = highest["value"]
    knot["left"] = excise(knot["left"], highest["value"])
    return knot


def replay_tree_ops(steps: list) -> list:
    if not isinstance(steps, list):
        raise ValueError("steps must be a list")
    root = None
    for step in steps:
        if not isinstance(step, str) or re.fullmatch(r"(?:add|drop):-?\d+", step) is None:
            raise ValueError("every step must read add:<n> or drop:<n>")
        verb, _, digits = step.partition(":")
        value = int(digits)
        if verb == "add":
            root = graft(root, value)
        else:
            root = excise(root, value)
    out = []
    stack = [] if root is None else [root]
    while stack:
        knot = stack.pop()
        out.append(knot["value"])
        if knot["right"] is not None:
            stack.append(knot["right"])
        if knot["left"] is not None:
            stack.append(knot["left"])
    return out
