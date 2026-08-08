"""A tag tree drawn down to a measured width."""

import re

HEAD = re.compile(r"[a-z]+")
WORD = re.compile(r"[a-z0-9]+")


def _check(thing):
    if isinstance(thing, str):
        if WORD.fullmatch(thing) is None:
            raise ValueError("a word is small letters and digits only")
        return
    if not isinstance(thing, dict):
        raise ValueError("an item is either a word or a tag")
    if "head" not in thing or "items" not in thing:
        raise ValueError("a tag needs both head and items")
    if not isinstance(thing["head"], str) or HEAD.fullmatch(thing["head"]) is None:
        raise ValueError("a head is small letters only")
    if not isinstance(thing["items"], list):
        raise ValueError("items must be a list")
    for item in thing["items"]:
        _check(item)


def _tight(thing):
    if isinstance(thing, str):
        return thing
    return thing["head"] + "(" + ", ".join(_tight(i) for i in thing["items"]) + ")"


def fit_tag_lines(node: dict, width: int) -> str:
    if not isinstance(width, int) or isinstance(width, bool) or width < 1:
        raise ValueError("the width must be a whole number of one or more")
    if isinstance(node, str):
        raise ValueError("an item is either a word or a tag")
    _check(node)

    def draw(thing, depth):
        pad = "  " * depth
        one = _tight(thing)
        if isinstance(thing, str) or len(pad) + len(one) <= width:
            return [pad + one]
        lines = [pad + thing["head"] + "("]
        last = len(thing["items"]) - 1
        for index, item in enumerate(thing["items"]):
            kid = draw(item, depth + 1)
            if index < last:
                kid[-1] += ","
            lines.extend(kid)
        lines.append(pad + ")")
        return lines

    return "\n".join(draw(node, 0))
