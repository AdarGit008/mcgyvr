"""Close out a stockroom count sheet after a day's receive and issue moves."""

import re


def closing_sheet(opening: str, moves: str) -> str:
    if not isinstance(opening, str) or not isinstance(moves, str):
        raise ValueError("closing_sheet expects two strings")

    def parse_sheet(text):
        held = {}
        if text == "":
            return held
        for part in text.split(";"):
            name, colon, count = part.partition(":")
            if colon == "":
                raise ValueError(f"sheet entry has no colon: {part}")
            if re.fullmatch(r"[a-z]+", name) is None:
                raise ValueError(f"bad item name: {part}")
            if re.fullmatch(r"0|[1-9]\d*", count) is None:
                raise ValueError(f"bad count: {part}")
            if name in held:
                raise ValueError(f"duplicate sheet entry: {name}")
            held[name] = int(count)
        return held

    def apply_moves(held, text):
        if text == "":
            return
        for part in text.split(";"):
            match = re.fullmatch(r"([a-z]+)([+-])([1-9]\d*)", part)
            if match is None:
                raise ValueError(f"malformed move: {part}")
            name, mark, qty_text = match.groups()
            qty = int(qty_text)
            if mark == "+":
                held[name] = held.get(name, 0) + qty
                continue
            if name not in held:
                raise ValueError(f"issue of an item not on the sheet: {name}")
            if qty > held[name]:
                raise ValueError(f"issue of {qty} exceeds the {held[name]} on hand")
            held[name] = held[name] - qty

    held = parse_sheet(opening)
    apply_moves(held, moves)
    entries = []
    for name in sorted(held):
        if held[name] != 0:
            entries.append(f"{name}:{held[name]}")
    return ";".join(entries)
