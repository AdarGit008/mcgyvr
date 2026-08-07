"""The quantity a gauge formula names, read out of a table."""

import re

VALUE = re.compile(r"0|-?[1-9]\d*")
PART = re.compile(r"([a-z]+)(?:\^(-?[1-9]\d*))?")
LABEL = re.compile(r"[a-z]+")


def _read_quantity(text):
    if not isinstance(text, str):
        raise ValueError("a quantity must be a string")
    head, space, tail = text.partition(" ")
    if VALUE.fullmatch(head) is None:
        raise ValueError("a quantity begins with a whole number")
    units = {}
    if space:
        if tail == "":
            raise ValueError("a unit text may not be empty")
        for part in tail.split("*"):
            found = PART.fullmatch(part)
            if found is None:
                raise ValueError("a malformed unit part")
            if found.group(1) in units:
                raise ValueError("a unit name appears twice in one unit text")
            units[found.group(1)] = (
                1 if found.group(2) is None else int(found.group(2))
            )
    return {"value": int(head), "units": units}


def _tidy(units):
    return {name: power for name, power in units.items() if power != 0}


def _read_product(text, book):
    at = 0
    running = None
    op = "*"
    while True:
        label = ""
        while at < len(text) and text[at] not in ("*", "/"):
            label += text[at]
            at += 1
        if label == "":
            raise ValueError("an operand is missing")
        if LABEL.fullmatch(label) is None:
            raise ValueError("a label is a run of small letters")
        if label not in book:
            raise ValueError("the table has no such label")
        one = book[label]
        if running is None:
            running = {"value": one["value"], "units": dict(one["units"])}
        elif op == "*":
            running["value"] *= one["value"]
            for name, power in one["units"].items():
                running["units"][name] = running["units"].get(name, 0) + power
        else:
            if one["value"] == 0:
                raise ValueError("a divisor's number may not be zero")
            if running["value"] % one["value"] != 0:
                raise ValueError("that division does not come out whole")
            running["value"] //= one["value"]
            for name, power in one["units"].items():
                running["units"][name] = running["units"].get(name, 0) - power
        if at >= len(text):
            break
        op = text[at]
        at += 1
    running["units"] = _tidy(running["units"])
    return running


def read_gauge_formula(table: dict, formula: str) -> str:
    if not isinstance(table, dict):
        raise ValueError("the table must be a mapping")
    book = {}
    for label, text in table.items():
        if not isinstance(label, str) or LABEL.fullmatch(label) is None:
            raise ValueError("a table label is a run of small letters")
        book[label] = _read_quantity(text)
    if not isinstance(formula, str) or formula == "":
        raise ValueError("the formula must be a non-empty string")

    total = None
    for piece in formula.split("+"):
        run = _read_product(piece, book)
        if total is None:
            total = run
        else:
            if total["units"] != run["units"]:
                raise ValueError("unlike quantities cannot be added")
            total = {"value": total["value"] + run["value"], "units": total["units"]}

    names = sorted(total["units"])
    head = str(total["value"])
    if not names:
        return head
    body = "*".join(
        name if total["units"][name] == 1 else f"{name}^{total['units'][name]}"
        for name in names
    )
    return f"{head} {body}"
